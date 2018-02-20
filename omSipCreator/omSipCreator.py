#! /usr/bin/env python
"""
SIP Creator for Offline Media Images.
"""

import sys
import os
import shutil
import glob
import imp
import argparse
import codecs
import csv
import logging
from operator import itemgetter
from itertools import groupby
from . import config
from . import checksums
from .shared import errorExit
from .ppn import processPPN


# Bind raw_input (Python 3) to input (Python 2)
# Source: http://stackoverflow.com/a/21731110/1209004
try:
    input = raw_input
except NameError:
    pass


# Script name
config.scriptPath, config.scriptName = os.path.split(sys.argv[0])

# scriptName is empty when called from Java/Jython, so this needs a fix
if len(config.scriptName) == 0:
    config.scriptName = 'omSipCreator'

__version__ = "0.4.11"
config.version = __version__

# Create parser
parser = argparse.ArgumentParser(
    description="SIP Creator for Offline Media Images")


def main_is_frozen():
    """Returns True if maijn function is frozen
    (e.g. PyInstaller/Py2Exe executable)
    """
    return (hasattr(sys, "frozen") or  # new py2exe
            hasattr(sys, "importers") or  # old py2exe
            imp.is_frozen("__main__"))  # tools/freeze


def get_main_dir():
    """Reurns installation directory"""
    if main_is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(sys.argv[0])


def checkFileExists(fileIn):
    """Check if file exists and exit if not"""
    if not os.path.isfile(fileIn):
        msg = "file " + fileIn + " does not exist!"
        sys.stderr.write("Error: " + msg + "\n")
        sys.exit()


def get_immediate_subdirectories(a_dir, ignoreDirs):
    """Returns list of immediate subdirectories
    Directories that end with suffixes defined by ignoreDirs are ignored
    """
    subDirs = []
    for root, dirs, files in os.walk(a_dir):
        for myDir in dirs:
            ignore = False
            for ignoreDir in ignoreDirs:
                if myDir.endswith(ignoreDir):
                    ignore = True
            if not ignore:
                subDirs.append(os.path.abspath(os.path.join(root, myDir)))

    return subDirs


def parseCommandLine():
    """Parse command-line arguments"""

    # Sub-parsers for check and write commands

    subparsers = parser.add_subparsers(help='sub-command help',
                                       dest='subcommand')
    parser_verify = subparsers.add_parser('verify',
                                          help='only verify input batch without writing SIPs')
    parser_verify.add_argument('batchIn',
                               action="store",
                               type=str,
                               help="input batch")
    parser_prune = subparsers.add_parser('prune',
                                         help="verify input batch, then write 'pruned' version \
                         of batch that omits all PPNs that have errors. Write PPNs with \
                         errors to a separate batch.")
    parser_prune.add_argument('batchIn',
                              action="store",
                              type=str,
                              help="input batch")
    parser_prune.add_argument('batchErr',
                              action="store",
                              type=str,
                              help="name of batch that will contain all PPNs with errors")
    parser_write = subparsers.add_parser('write',
                                         help="verify input batch and write SIPs. Before using \
                         'write' first run the 'verify' command and fix any reported errors.")
    parser_write.add_argument('batchIn',
                              action="store",
                              type=str,
                              help="input batch")
    parser_write.add_argument('dirOut',
                              action="store",
                              type=str,
                              help="output directory where SIPs are written")
    parser.add_argument('--version', '-v',
                        action='version',
                        version=__version__)

    # Parse arguments
    args = parser.parse_args()

    return args


def printHelpAndExit():
    """Print usage message and exit"""
    print('')
    parser.print_help()
    sys.exit()


def main():
    """Main CLI function"""

    # Set up logger
    logFile = "omsipcreator.log"
    # Suppress info messages from requests module
    logging.getLogger("requests").setLevel(logging.WARNING)
    logFormatter = logging.Formatter('%(levelname)s - %(message)s')
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    # Locate package directory
    packageDir = os.path.dirname(os.path.abspath(__file__))
    # Tools directory
    toolsDirUser = os.path.join(packageDir, 'tools')

    # Batch manifest file - basic capture-level metadata about carriers
    fileBatchManifest = "manifest.csv"
    fileBatchLog = "batch.log"

    # Header values of mandatory columns in batch manifest
    requiredColsBatchManifest = ['jobID',
                                 'PPN',
                                 'volumeNo',
                                 'carrierType',
                                 'title',
                                 'volumeID',
                                 'success',
                                 'containsAudio',
                                 'containsData',
                                 'cdExtra']

    # Controlled vocabulary for 'carrierType' field
    carrierTypeAllowedValues = ['cd-rom',
                                'cd-audio',
                                'dvd-rom',
                                'dvd-video']

    # Define name spaces for METS output
    config.mets_ns = 'http://www.loc.gov/METS/'
    config.mods_ns = 'http://www.loc.gov/mods/v3'
    config.premis_ns = 'http://www.loc.gov/premis/v3'
    config.ebucore_ns = 'urn:ebu:metadata-schema:ebucore'
    config.isolyzer_ns = 'https://github.com/KBNLresearch/isolyzer'
    config.cdInfo_ns = 'https://www.gnu.org/software/libcdio/libcdio.html#cd_002dinfo' # TODO: is this a proper namespace?
    config.dfxml_ns = 'http://www.forensicswiki.org/wiki/Category:Digital_Forensics_XML'
    config.xlink_ns = 'http://www.w3.org/1999/xlink'
    config.xsi_ns = 'http://www.w3.org/2001/XMLSchema-instance'
    config.metsSchema = 'http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd'
    config.modsSchema = 'http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods-3-4.xsd'
    config.premisSchema = 'http://www.loc.gov/premis/v3 https://www.loc.gov/standards/premis/premis.xsd'
    config.ebucoreSchema = 'https://raw.githubusercontent.com/ebu/ebucore/master/ebucore.xsd'

    config.NSMAP = {"mets": config.mets_ns,
                    "mods": config.mods_ns,
                    "premis": config.premis_ns,
                    "ebucore": config.ebucore_ns,
                    "isolyzer": config.isolyzer_ns,
                    "cd-info": config.cdInfo_ns,
                    "dfxml": config.dfxml_ns,
                    "xlink": config.xlink_ns,
                    "xsi": config.xsi_ns}

    # Counters for number of errors and warnings
    config.errors = 0
    config.warnings = 0

    # List of failed PPNs (used for pruning a batch)
    config.failedPPNs = []

    # Set encoding of the terminal to UTF-8
    if sys.version.startswith("2"):
        out = codecs.getwriter("UTF-8")(sys.stdout)
        err = codecs.getwriter("UTF-8")(sys.stderr)
    elif sys.version.startswith("3"):
        out = codecs.getwriter("UTF-8")(sys.stdout.buffer)
        err = codecs.getwriter("UTF-8")(sys.stderr.buffer)

    # Flag that indicates if SIPs will be written
    config.createSIPs = False

    # Flag that indicates if prune option is used
    config.pruneBatch = False

    # Get input from command line
    args = parseCommandLine()
    action = args.subcommand
    if action is None:
        # Exit and print help message if command line is empty
        printHelpAndExit()

    batchIn = os.path.normpath(args.batchIn)

    if action == "write":
        dirOut = os.path.normpath(args.dirOut)
        config.createSIPs = True
    elif action == "prune":
        batchErr = os.path.normpath(args.batchErr)
        dirOut = None
        config.pruneBatch = True
    else:
        # Dummy value
        dirOut = None

    # Path to MediaInfo
    if sys.platform is "win32":
        config.mediaInfoExe = os.path.join(
            toolsDirUser, 'mediainfo', 'MediaInfo.exe')
    elif sys.platform in ["linux", "linux2"]:
        config.mediaInfoExe = "/usr/bin/mediainfo"
    checkFileExists(config.mediaInfoExe)

    # Check if batch dir exists
    if not os.path.isdir(batchIn):
        logging.fatal("input batch directory does not exist")
        config.errors += 1
        errorExit(config.errors, config.warnings)

    # Get listing of all directories (not files) in batch dir (used later for completeness check)
    # Note: all entries as full, absolute file paths!

    # Define dirs to ignore (jobs and jobsFailed)
    ignoreDirs = ["jobs", "jobsFailed"]

    dirsInBatch = get_immediate_subdirectories(batchIn, ignoreDirs)

    # List for storing directories as extracted from carrier metadata file (see below)
    # Note: all entries as full, absolute file paths!
    dirsInMetaCarriers = []

    # Check if batch manifest exists
    batchManifest = os.path.join(batchIn, fileBatchManifest)
    if not os.path.isfile(batchManifest):
        logging.fatal("file " + batchManifest + " does not exist")
        config.errors += 1
        errorExit(config.errors, config.warnings)

    # Read batch manifest as CSV and import header and
    # row data to 2 separate lists
    try:
        if sys.version.startswith('3'):
            # Py3: csv.reader expects file opened in text mode
            fBatchManifest = open(batchManifest, "r", encoding="utf-8")
        elif sys.version.startswith('2'):
            # Py2: csv.reader expects file opened in binary mode
            fBatchManifest = open(batchManifest, "rb")
        batchManifestCSV = csv.reader(fBatchManifest)
        headerBatchManifest = next(batchManifestCSV)
        rowsBatchManifest = [row for row in batchManifestCSV]
        fBatchManifest.close()
    except IOError:
        logging.fatal("cannot read " + batchManifest)
        config.errors += 1
        errorExit(config.errors, config.warnings)
    except csv.Error:
        logging.fatal("error parsing " + batchManifest)
        config.errors += 1
        errorExit(config.errors, config.warnings)

    # Iterate over rows and check that number of columns
    # corresponds to number of header columns.
    # Remove any empty list elements (e.g. due to EOL chars)
    # to avoid trouble with itemgetter

    colsHeader = len(headerBatchManifest)

    rowCount = 1
    for row in rowsBatchManifest:
        rowCount += 1
        colsRow = len(row)
        if colsRow == 0:
            rowsBatchManifest.remove(row)
        elif colsRow != colsHeader:
            logging.fatal("wrong number of columns in row " +
                          str(rowCount) + " of '" + batchManifest + "'")
            config.errors += 1
            errorExit(config.errors, config.warnings)

    # Create output directory if in SIP creation mode
    if config.createSIPs:
        # Remove output dir tree if it exists already
        # Potentially dangerous, so ask for user confirmation
        if os.path.isdir(dirOut):

            out.write("This will overwrite existing directory '" + dirOut +
                      "' and remove its contents!\nDo you really want to proceed (Y/N)? > ")
            response = input()

            if response.upper() == "Y":
                try:
                    shutil.rmtree(dirOut)
                except OSError:
                    logging.fatal("cannot remove '" + dirOut + "'")
                    config.errors += 1
                    errorExit(config.errors, config.warnings)

        # Create new dir
        try:
            os.makedirs(dirOut)
        except OSError:
            logging.fatal("cannot create '" + dirOut + "'")
            config.errors += 1
            errorExit(config.errors, config.warnings)

    # ********
    # ** Process batch manifest **
    # ********

    # Check that there is exactly one occurrence of each mandatory column

    for requiredCol in requiredColsBatchManifest:
        occurs = headerBatchManifest.count(requiredCol)
        if occurs != 1:
            logging.fatal("found " + str(occurs) + " occurrences of column '" +
                          requiredCol + "' in " + batchManifest + " (expected 1)")
            config.errors += 1
            # No point in continuing if we end up here ...
            errorExit(config.errors, config.warnings)

    # Set up dictionary to store header fields and corresponding column numbers
    colsBatchManifest = {}

    col = 0
    for header in headerBatchManifest:
        colsBatchManifest[header] = col
        col += 1

    # Sort rows by PPN
    rowsBatchManifest.sort(key=itemgetter(1))

    # Group by PPN
    metaCarriersByPPN = groupby(rowsBatchManifest, itemgetter(1))

    # ********
    # ** Iterate over PPNs**
    # ********

    for PPN, carriers in metaCarriersByPPN:
        logging.info("Processing PPN " + PPN)
        processPPN(PPN, carriers, dirOut, colsBatchManifest, batchIn,
                   dirsInMetaCarriers, carrierTypeAllowedValues)

    # Check if directories that are part of batch are all represented in carrier metadata file
    # (reverse already covered by checks above)

    # Diff as list
    diffDirs = list(set(dirsInBatch) - set(dirsInMetaCarriers))

    # Report each item in list as an error

    for directory in diffDirs:
        logging.error("PPN " + PPN + ": directory '" + directory +
                      "' not referenced in '" + batchManifest + "'")
        config.errors += 1
        config.failedPPNs.append(PPN)

    # Summarise no. of warnings / errors
    logging.info("Verify / write resulted in " + str(config.errors) +
                 " errors and " + str(config.warnings) + " warnings")

    # Reset warnings/errors
    config.errors = 0
    config.warnings = 0

    # Get all unique values in failedPPNs by converting to a set (and then back to a list)
    config.failedPPNs = (list(set(config.failedPPNs)))

    if config.pruneBatch and config.failedPPNs != []:

        logging.info("Start pruning")

        # Check if batchErr is an existing directory. If yes,
        # prompt user to confirm that it will be overwritten

        if os.path.isdir(batchErr):

            out.write("\nThis will overwrite existing directory '" + batchErr +
                      "' and remove its contents!\nDo you really want to proceed (Y/N)? > ")
            response = input()

            if response.upper() == "Y":
                try:
                    shutil.rmtree(batchErr)
                except OSError:
                    logging.fatal("cannot remove '" + batchErr + "'")
                    config.errors += 1
                    errorExit(config.errors, config.warnings)
            else:
                logging.error("exiting because user pressed 'N'")
                errorExit(config.errors, config.warnings)

        # Create batchErr directory

        try:
            os.makedirs(batchErr)
        except (OSError, IOError):
            logging.fatal("Cannot create directory '" + batchErr + "'")
            config.errors += 1
            errorExit(config.errors, config.warnings)

        # Add batch manifest to batchErr directory
        batchManifestErr = os.path.join(batchErr, fileBatchManifest)

        # Add temporary (updated) batch manifest to batchIn
        fileBatchManifestTemp = "tmp.csv"
        batchManifestTemp = os.path.join(batchIn, fileBatchManifestTemp)

        try:
            if sys.version.startswith('3'):
                # Py3: csv.reader expects file opened in text mode
                fbatchManifestErr = open(
                    batchManifestErr, "w", encoding="utf-8")
                fbatchManifestTemp = open(
                    batchManifestTemp, "w", encoding="utf-8")
            elif sys.version.startswith('2'):
                # Py2: csv.reader expects file opened in binary mode
                fbatchManifestErr = open(batchManifestErr, "wb")
                fbatchManifestTemp = open(batchManifestTemp, "wb")
        except IOError:
            logging.fatal("cannot write batch manifest")
            config.errors += 1
            errorExit(config.errors, config.warnings)

        # Create CSV writer objects
        csvErr = csv.writer(fbatchManifestErr, lineterminator='\n')
        csvTemp = csv.writer(fbatchManifestTemp, lineterminator='\n')

        # Write header rows to batch manifests
        csvErr.writerow(headerBatchManifest)
        csvTemp.writerow(headerBatchManifest)

        # Iterate over all entries in batch manifest

        for row in rowsBatchManifest:
            jobID = row[0]
            PPN = row[1]

            if PPN in config.failedPPNs:
                # If PPN is in list of failed PPNs then add record to error batch

                # Image path for this jobID in input, pruned and error batch
                imagePathIn = os.path.normpath(os.path.join(batchIn, jobID))
                imagePathErr = os.path.normpath(os.path.join(batchErr, jobID))

                imagePathInAbs = os.path.abspath(imagePathIn)
                imagePathErrAbs = os.path.abspath(imagePathErr)

                if os.path.isdir(imagePathInAbs):

                    # Create directory in error batch
                    try:
                        os.makedirs(imagePathErrAbs)
                    except (OSError, IOError):
                        logging.error("jobID " + jobID +
                                      ": could not create directory '" +
                                      imagePathErrAbs)
                        config.errors += 1

                    # All files in directory
                    allFiles = glob.glob(imagePathInAbs + "/*")

                    # Copy all files to error batch and do post-copy checksum verification
                    logging.info("Copying files to error batch")

                    for fileIn in allFiles:
                        # File base name
                        fileBaseName = os.path.basename(fileIn)

                        # Path to copied file
                        fileErr = os.path.join(imagePathErrAbs, fileBaseName)

                        # Copy file to batchErr
                        try:
                            shutil.copy2(fileIn, fileErr)
                        except (IOError, OSError):
                            logging.error("jobID " + jobID + ": cannot copy '" +
                                          fileIn + "' to '" + fileErr + "'")
                            config.errors += 1

                        # Verify checksum
                        checksumIn = checksums.generate_file_sha512(fileIn)
                        checksumErr = checksums.generate_file_sha512(fileErr)

                        if checksumIn != checksumErr:
                            logging.error("jobID " + jobID + ": checksum of '" +
                                          fileIn + "' does not match '" + fileErr + "'")
                            config.errors += 1

                # Write row to error batch manifest
                logging.info("Writing batch manifest entry (batchErr)")
                csvErr.writerow(row)

                # Remove directory from input batch
                if os.path.isdir(imagePathInAbs):
                    logging.info("Removing  directory '" +
                                 imagePathInAbs + "' from batchIn")
                    try:
                        shutil.rmtree(imagePathInAbs)
                    except OSError:
                        logging.error("cannot remove '" + imagePathInAbs + "'")
                        config.errors += 1
            else:
                # Write row to temp batch manifest
                logging.info("Writing batch manifest entry (batchIn)")
                csvTemp.writerow(row)

        fbatchManifestErr.close()
        fbatchManifestTemp.close()

        # Rename original batchManifest to '.old' extension
        fileBatchManifestOld = os.path.splitext(fileBatchManifest)[0] + ".old"
        batchManifestOld = os.path.join(batchIn, fileBatchManifestOld)
        os.rename(batchManifest, batchManifestOld)

        # Rename batchManifestTemp to batchManifest
        os.rename(batchManifestTemp, batchManifest)

        logging.info("Saved old batch manifest in batchIn as '" +
                     fileBatchManifestOld + "'")

        # Copy batch log to error batch
        batchLogIn = os.path.join(batchIn, fileBatchLog)
        batchLogErr = os.path.join(batchErr, fileBatchLog)
        shutil.copy2(batchLogIn, batchLogErr)

        # Summarise no. of additional warnings / errors during pruning
        logging.info("Pruning resulted in additional " + str(config.errors) +
                     " errors and " + str(config.warnings) + " warnings")


if __name__ == "__main__":
    main()
