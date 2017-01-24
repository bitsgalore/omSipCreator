#! /usr/bin/env python

import sys
import os
import shutil
import ntpath
import glob
import imp
import argparse
import codecs
import csv
import hashlib
from operator import itemgetter
from itertools import groupby
from lxml import etree
from kbapi import sru

# Bind raw_input (Python 3) to input (Python 2)
# Source: http://stackoverflow.com/a/21731110/1209004
try:
   input = raw_input
except NameError:
   pass

"""

SIP Creator for Offline Media images.

NOTES
-----

## SIP structure

Current code based on multi-volume SIPS. But OAIS allows one to describe a composite object as an
Archival Information Collection (AIC). This may be a better solution, which would imply 
single-volume SIPs. See also:

http://qanda.digipres.org/1121/creation-practices-optical-carriers-that-multiple-volumes

## Quality checks on image files

Could be added as further refinement:

* ISO 'validation' (see also paper Woods & others)
* WAV validation (JHOVE?)

 """

# Script name
scriptPath, scriptName = os.path.split(sys.argv[0])

# scriptName is empty when called from Java/Jython, so this needs a fix
if len(scriptName) == 0:
    scriptName = 'omsipcreator'

__version__ = "0.2.0"

# Create parser
parser = argparse.ArgumentParser(
    description="SIP creation tool for optical media images")

# Classes for Carrier and IP entries
class Carrier:

    def __init__(self, IPIdentifier, IPIdentifierParent, imagePathFull, volumeNumber, carrierType):
        self.IPIdentifier = IPIdentifier
        self.IPIdentifierParent = IPIdentifierParent
        self.imagePathFull = imagePathFull
        self.volumeNumber = volumeNumber
        self.carrierType = carrierType

class IP:

    def __init__(self):
        self.carriers = []
        self.IPIdentifier = ""
        self.IPIdentifierParent = ""
        self.carrierType = ""

    def append(self,carrier):
        # Result of this is that below IP-level properties are inherited from last
        # appended carrier (values should be identical for all carriers within IP,
        # but important to do proper QA on this as results may be unexpected otherwise)
        self.carriers.append(carrier)
        self.IPIdentifier = carrier.IPIdentifier
        self.IPIdentifierParent = carrier.IPIdentifierParent
        self.carrierType = carrier.carrierType

def main_is_frozen():
    return (hasattr(sys, "frozen") or  # new py2exe
            hasattr(sys, "importers")  # old py2exe
            or imp.is_frozen("__main__"))  # tools/freeze

def get_main_dir():
    if main_is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(sys.argv[0])
 
def errorExit(errors,terminal):
    for error in errors:
        terminal.write("Error - " + error + "\n")
    sys.exit()
    
def get_immediate_subdirectories(a_dir):
    subDirs = []
    for root, dirs, files in os.walk(a_dir):
        for dir in dirs:
            subDirs.append(os.path.abspath(os.path.join(root, dir)))

    return(subDirs)

def readMD5(fileIn):
    # Read MD 5 file, return contents as nested list
    # Also strip away any file paths if they exist (return names only)

    try:
        data = []
        f = open(fileIn,"r")
        for row in f:
            rowSplit = row.split()
            # Second col contains file name. Strip away any path components if they are present
            fileName = rowSplit[1] # Raises IndexError if entry only 1 col (malformed MD5 file)!
            rowSplit[1] = ntpath.basename(fileName) 
            data.append(rowSplit)    
        f.close()
        return(data)
    except IOError:
        errors.append("cannot read '" + fileIn + "'")
        errorExit(errors,err)

def generate_file_md5(fileIn):
    # Generate MD5 hash of file
    # fileIn is read in chunks to ensure it will work with (very) large files as well
    # Adapted from: http://stackoverflow.com/a/1131255/1209004

    blocksize = 2**20
    m = hashlib.md5()
    with open(fileIn, "rb") as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

def generate_file_sha512(fileIn):
    # Generate sha512 hash of file
    # fileIn is read in chunks to ensure it will work with (very) large files as well
    # Adapted from: http://stackoverflow.com/a/1131255/1209004

    blocksize = 2**20
    m = hashlib.sha512()
    with open(fileIn, "rb") as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

     
def processCarrier(carrier, fileGrp, SIPPath, sipFileCounterStart):
    # Process contents of imagepath directory
    # TODO: * check file type / extension matches carrierType!
    # TODO: currently lots of file path manipulations which make things hard to read, 
    # could be better structured with more understandable naming conventions.
       
    # Counters used to assign file ORDER and IDs, sipFileCounter must be unique for
    # each file within SIP
    fileCounter = 1
    sipFileCounter = sipFileCounterStart
    
    # Mapping between carrierType and structmap TYPE field
    
    carrierTypeMap = {
        "cd-rom" : "disk image",
        "dvd-rom" : "disk image",
        "dvd-video" : "disk image",
        "cd-audio" : "audio track"
        }
    
    # Default state of flag that is set to "True" if checksums are missing 
    skipChecksumVerification = False
    
    # All files in directory
    allFiles = glob.glob(carrier.imagePathFull + "/*")
               
    # Find MD5 files (by extension)
    MD5Files = [i for i in allFiles if i.endswith('.md5')]
      
    # Number of MD5 files must be exactly 1
    noMD5Files = len(MD5Files)
    
    if noMD5Files != 1:
        errors.append("IP " + carrier.IPIdentifier + ": found " + str(noMD5Files) + " '.md5' files in directory '" \
        + carrier.imagePathFull + "', expected 1")
        # If we end up here, checksum file either does not exist, or it is ambiguous 
        # which file should be used. No point in doing the checksum verification in that case.  
        skipChecksumVerification = True

    # Any other files (ISOs, audio files)
    otherFiles = [i for i in allFiles if not i.endswith('.md5')]
    noOtherFiles = len(otherFiles)
    
    if noOtherFiles == 0:
        errors.append("IP " + carrier.IPIdentifier + ": found no files in directory '" \
        + carrier.imagePathFull) 

    if skipChecksumVerification == False:
        # Read contents of checksum file to list
        MD5FromFile = readMD5(MD5Files[0])
        
        # Sort ascending by file name - this ensures correct order when making structMap
        MD5FromFile.sort(key=itemgetter(1))
                
        # List which to store names of all files that are referenced in the MD5 file
        allFilesinMD5 = []
        for entry in MD5FromFile:
            md5Sum = entry[0]
            fileName = entry[1] # Raises IndexError if entry only 1 col (malformed MD5 file)!
            # Normalise file path relative to imagePath
            fileNameWithPath = os.path.normpath(carrier.imagePathFull + "/" + fileName)
            
            # Calculate MD5 hash of actual file
            md5SumCalculated = generate_file_md5(fileNameWithPath)
                                   
            if md5SumCalculated != md5Sum:
                errors.append("IP " + carrier.IPIdentifier + ": checksum mismatch for file '" + \
                fileNameWithPath + "'")
                
            # Get file size and append to MD5FromFile list (needed later for METS file entry)
            entry.append(str(os.path.getsize(fileNameWithPath)))
                        
            # Append file name to list 
            allFilesinMD5.append(fileNameWithPath)
            
        # Check if any files in directory are missing from MD5 file
        for f in otherFiles:
            print(f)
            if f not in allFilesinMD5:
                errors.append("IP " + carrier.IPIdentifier + ": file '" + f + \
                "' not referenced in '" + \
                MD5Files[0] + "'")
        
        # Create METS div entry (will remain empty if createSIPs != True)
        divDiscName = etree.QName(mets_ns, "div")
        divDisc = etree.Element(divDiscName, nsmap = NSMAP)
        divDisc.attrib["TYPE"] = carrier.carrierType    
        divDisc.attrib["ORDER"] = carrier.volumeNumber
                        
        if createSIPs == True:
       
            # Create Volume directory
            dirVolume = os.path.join(SIPPath, carrier.carrierType, carrier.volumeNumber)
            try:
                os.makedirs(dirVolume)
            except OSError or IOError:
                errors.append("IP " + carrier.IPIdentifier + ": cannot create '" + dirVolume + "'" )
                errorExit(errors,err)
            
            # Copy files to SIP Volume directory
            
            # Get file names from MD5 file, as this is the easiest way to make
            # post-copy checksum verification work.
            for entry in MD5FromFile:
                md5Sum = entry[0]
                fileName = entry[1]
                fileSize = entry[2]
                # Generate unique file ID
                fileID = "FILE_" + str(sipFileCounter).zfill(3) 
                # Construct path relative to volume directory
                fSIP = os.path.join(dirVolume,fileName)
                try:
                    # Copy to volume dir
                    shutil.copy2(os.path.join(carrier.imagePathFull,fileName),fSIP)
                except OSError:
                    errors.append("IP " + carrier.IPIdentifier + ": cannot copy '"\
                    + fileName + "' to '" + fSIP + "'")
                    errorExit(errors,err)
            
                # Calculate MD5 hash of copied file, and verify against known value
                md5SumCalculated = generate_file_md5(fSIP)                               
                if md5SumCalculated != md5Sum:
                    errors.append("IP " + carrier.IPIdentifier + ": checksum mismatch for file '" + \
                    fSIP + "'")
                    
                # Calculate Sha512 checksum
                sha512Sum = generate_file_sha512(fSIP)
               
                # Create METS file and FLocat elements
                fileElt = etree.SubElement(fileGrp, "{%s}file" %(mets_ns))
                fileElt.attrib["ID"] = fileID 
                fileElt.attrib["SIZE"] = fileSize
                # TODO: add SEQ and CREATED, DMDID attributes as well
                
                fLocat = etree.SubElement(fileElt, "{%s}FLocat" %(mets_ns))
                fLocat.attrib["LOCTYPE"] = "URL"
                # File locations relative to SIP root (= location of METS file)
                #fLocat.attrib[etree.QName(xlink_ns, "href")] = "file://./" + os.path.join(carrier.carrierType, carrier.volumeNumber ,fileName)                
                fLocat.attrib[etree.QName(xlink_ns, "href")] = "file://./" + carrier.carrierType + "/" + carrier.volumeNumber + "/" + fileName
                
                # Add MIME type and checksum to file element
                # TODO replace by proper signature-based identification (e.g. Fido) 
                if fileName.endswith(".iso"):
                    mimeType = "application/x-iso9660"
                elif fileName.endswith(".wav"):
                    mimeType = "audio/x-wav"
                else:
                    mimeType = "application/octet-stream"   
                fileElt.attrib["MIMETYPE"] = mimeType
                #fileElt.attrib["CHECKSUM"] = md5Sum
                #fileElt.attrib["CHECKSUMTYPE"] = "MD5"
                fileElt.attrib["CHECKSUM"] = sha512Sum
                fileElt.attrib["CHECKSUMTYPE"] = "SHA-512"
                
                # TODO: check if mimeType values matches carrierType (e.g. no audio/x-wav if cd-rom, etc.)
                                
                # Create track divisor element for structmap
                divFile = etree.SubElement(divDisc, "{%s}div" %(mets_ns))
                divFile.attrib["TYPE"] = carrierTypeMap[carrier.carrierType]
                divFile.attrib["ORDER"] = str(fileCounter)
                fptr = etree.SubElement(divFile, "{%s}fptr" %(mets_ns))
                fptr.attrib["FILEID"] = fileID
                
                fileCounter += 1
                sipFileCounter += 1
    else:
        # Dummy value, not used
        divDisc = etree.Element('rubbish')
    return(fileGrp, divDisc, sipFileCounter)             
                
   
def createMODS(IP):
    # Create MODS metadata based on records in GGC
    # Dublin Core to MODS mapping follows http://www.loc.gov/standards/mods/dcsimple-mods.html
    # General structure: bibliographic md is wrapped in relatedItem / type = host element
    
    # Dictionary maps carrier types  to MODS resource types 
    resourceTypeMap = {
        "cd-rom" : "software, multimedia",
        "dvd-rom" : "software, multimedia",
        "dvd-video" : "moving image",
        "cd-audio" : "sound recording"
        }

    IPIdentifier = IP.IPIdentifier
    PPNParent = IP.IPIdentifierParent
    carrierType = IP.carrierType
    
    # Create MODS element
    modsName = etree.QName(mods_ns, "mods")
    mods = etree.Element(modsName, nsmap = NSMAP)
                            
    # SRU search string (searches on dc:identifier field)
    sruSearchString = '"PPN=' + PPNParent + '"'
    response = sru.search(sruSearchString,"GGC")
    
    # This should return exactly one record. Return error if this is not the case
    noGGCRecords = response.sru.nr_of_records
    if noGGCRecords != 1:
        errors.append("IP " + IPIdentifier + ": search for PPN=" + PPNParent + " returned " + \
            str(noGGCRecords) + " catalogue records (expected 1)")
    
    # Select first record
    try:
        record = next(response.records)
        # Extract metadata
        titles = record.titles
        creators = record.creators
        contributors = record.contributors
        publishers = record.publishers
        dates = record.dates
        subjectsBrinkman = record.subjectsBrinkman
        annotations = record.annotations
        identifiersURI = record.identifiersURI
        identifiersISBN = record.identifiersISBN
        recordIdentifiersURI = record.recordIdentifiersURI
        collectionIdentifiers = record.collectionIdentifiers
    except StopIteration:
        # Create empty lists fot all metadata fields in case noGGCRecords = 0
        titles = []
        creators = []
        contributors = []
        publishers = []
        dates = []
        subjectsBrinkman = []
        annotations = []
        identifiersURI = []
        identifiersISBN = []
        recordIdentifiersURI = []
        collectionIdentifiers = []
          
    # Create MODS entries
    
    for title in titles:
        modsTitleInfo = etree.SubElement(mods, "{%s}titleInfo" %(mods_ns))
        modsTitle = etree.SubElement(modsTitleInfo, "{%s}title" %(mods_ns))
        modsTitle.text = title
          
    for creator in creators:
        modsName = etree.SubElement(mods, "{%s}name" %(mods_ns))
        modsNamePart = etree.SubElement(modsName, "{%s}namePart" %(mods_ns))
        modsNamePart.text = creator
        modsRole =  etree.SubElement(modsName, "{%s}role" %(mods_ns))
        modsRoleTerm =  etree.SubElement(modsRole, "{%s}roleTerm" %(mods_ns))
        modsRoleTerm.attrib["type"] = "text"
        modsRoleTerm.text = "creator"
        
    for contributor in contributors:
        modsName = etree.SubElement(mods, "{%s}name" %(mods_ns))
        modsNamePart = etree.SubElement(modsName, "{%s}namePart" %(mods_ns))
        modsNamePart.text = contributor
        modsRole =  etree.SubElement(modsName, "{%s}role" %(mods_ns))
        modsRoleTerm =  etree.SubElement(modsRole, "{%s}roleTerm" %(mods_ns))
        modsRoleTerm.attrib["type"] = "text"
        modsRoleTerm.text = "contributor"
    
    for publisher in publishers:
        modsOriginInfo = etree.SubElement(mods, "{%s}originInfo" %(mods_ns))
        modsOriginInfo.attrib["displayLabel"] = "publisher"
        modsPublisher = etree.SubElement(modsOriginInfo, "{%s}publisher" %(mods_ns))
        modsPublisher.text = publisher
                 
    for date in dates:
        # Note that DC date isn't necessarily issue date, and LoC DC to MODS mapping
        # suggests that dateOther be used as default. However KB Metadata model
        # only recognises dateIssued, so we'll use that. 
        modsOriginInfo = etree.SubElement(mods, "{%s}originInfo" %(mods_ns))
        modsDateIssued = etree.SubElement(modsOriginInfo, "{%s}dateIssued" %(mods_ns))
        modsDateIssued.text = date
    
    # TODO: perhaps add authority and language attributes
    modsSubject = etree.SubElement(mods, "{%s}subject" %(mods_ns))    
    for subjectBrinkman in subjectsBrinkman:
        modsTopic = etree.SubElement(modsSubject, "{%s}topic" %(mods_ns))
        modsTopic.text = subjectBrinkman
        
    modsTypeOfResource = etree.SubElement(mods, "{%s}typeOfResource" %(mods_ns))
    modsTypeOfResource.text = resourceTypeMap[carrierType]

    for annotation in annotations:
        modsNote = etree.SubElement(mods, "{%s}note" %(mods_ns))
        modsNote.text = annotation
    
    # This record establishes the link with the parent publication as it is described
    # in the GGC
    modsRelatedItem = etree.SubElement(mods, "{%s}relatedItem" %(mods_ns))
    modsRelatedItem.attrib["type"] = "host"

    modsIdentifierPPN = etree.SubElement(modsRelatedItem, "{%s}identifier" %(mods_ns))
    modsIdentifierPPN.attrib["type"] = "ppn"
    modsIdentifierPPN.text = PPNParent
    
    # NOTE: GGC record contain 2 URI- type identifiers:
    # 1. dc:identifier with URI of form: http://resolver.kb.nl/resolve?urn=PPN:236599380 (OpenURL?)
    # 2. dcx:recordIdentifier with URI of form: http://opc4.kb.nl/DB=1/PPN?PPN=236599380
    # URL 1. resolves to URL2, but not sure which one is more persistent?
    # Also a MODS RecordIdentifier field does exist, but it doesn't have a 'type' attribute
    # so we cannot specify it is a URI. For now both are included as 'identifier' elements
    #
    
    for identifierURI in identifiersURI:
        modsIdentifierURI = etree.SubElement(modsRelatedItem, "{%s}identifier" %(mods_ns))
        modsIdentifierURI.attrib["type"] = "uri"
        modsIdentifierURI.text = identifierURI
    """
    for recordIdentifierURI in recordIdentifiersURI:
        modsIdentifierURI = etree.SubElement(modsRelatedItem, "{%s}identifier" %(mods_ns))
        modsIdentifierURI.attrib["type"] = "uri"
        modsIdentifierURI.text = recordIdentifierURI
    """
    
    for identifierISBN in identifiersISBN:
        modsIdentifierISBN = etree.SubElement(modsRelatedItem, "{%s}identifier" %(mods_ns))
        modsIdentifierISBN.attrib["type"] = "isbn"
        modsIdentifierISBN.text = identifierISBN
   
    # Add some info on how MODS was generated
    modsRecordInfo = etree.SubElement(mods, "{%s}recordInfo" %(mods_ns))
    modsRecordOrigin = etree.SubElement(modsRecordInfo, "{%s}recordOrigin" %(mods_ns))
    originText = "Automatically generated by " + scriptName + " v. " + __version__  + " from records in KB Catalogue."
    modsRecordOrigin.text = originText
      
    return(mods)
       
def parseCommandLine():
    # Add arguments
    
    # Sub-parsers for check and write commands

    subparsers = parser.add_subparsers(help='sub-command help',
                        dest='subcommand')
    parser_verify = subparsers.add_parser('verify',
                        help='only verify input batch without writing SIPs')
    parser_verify.add_argument('batchIn',
                        action="store",
                        type=str,
                        help="input batch")
    parser_write = subparsers.add_parser('write',
                        help="verify input batch and write SIPs. Before using 'write' first \
                        run the 'verify' command and fix any reported errors.")
    parser_write.add_argument('batchIn',
                        action="store",
                        type=str,
                        help="input batch")
    parser_write.add_argument('dirOut',
                        action="store",
                        type=str,
                        help="output directory where SIPs are written")
    # Parse arguments
    args = parser.parse_args()

    return(args)
    

def processIP(IPIdentifier, carriers, dirOut, colsBatchManifest, batchIn, dirsInMetaCarriers, carrierTypeAllowedValues):

    # IP is IPIdentifier (by which we grouped data)
    # carriers is another iterator that contains individual carrier records
    
    # Create IP class instance for this IP
    thisIP = IP()
    
    # Create METS element for this SIP
    metsName = etree.QName(mets_ns, "mets")
    mets = etree.Element(metsName, nsmap = NSMAP)
    # Add schema reference
    mets.attrib[etree.QName(xsi_ns, "schemaLocation")] = "".join([metsSchema," ",modsSchema]) 
    # Subelements for dmdSec, fileSec and structMap
    dmdSec = etree.SubElement(mets, "{%s}dmdSec" %(mets_ns))
    # Add identifier
    # TODO: do we need any more than this? probably not ..
    dmdSec.attrib["ID"] = "dmdID"
    # Create mdWrap and xmlData child elements 
    mdWrap = etree.SubElement(dmdSec, "{%s}mdWrap" %(mets_ns))
    mdWrap.attrib["MDTYPE"] = "MODS"
    mdWrap.attrib["MDTYPEVERSION"] = "3.4"
    xmlData =  etree.SubElement(mdWrap, "{%s}xmlData" %(mets_ns))
    # Create fileSec and structMap elements
    fileSec = etree.SubElement(mets, "{%s}fileSec" %(mets_ns))
    fileGrp = etree.SubElement(fileSec, "{%s}fileGrp" %(mets_ns))
    structMap = etree.SubElement(mets, "{%s}structMap" %(mets_ns))
    # Add top-level divisor element to structMap
    structDivTop = etree.SubElement(structMap, "{%s}div" %(mets_ns))
    structDivTop.attrib["TYPE"] = "physical"
    structDivTop.attrib["LABEL"] = "volumes"
    
    # Initialise counter that is used to assign file IDs
    fileCounterStart = 1
    
    # Dummy value for dirSIP (needed if createSIPs = False)
    dirSIP = "rubbish" 
     
    if createSIPs == True:
        # Create SIP directory
        dirSIP = os.path.join(dirOut,IPIdentifier)
        try:
            os.makedirs(dirSIP)
        except OSError:
            errors.append("cannot create '" + dirSIP + "'" )
            errorExit(errors,err)
     
    # TODO: perhaps we can validate PPN, based on conventions/restrictions?

    # Set up lists for all record fields in this IP (needed for verifification only)
    IPIdentifiersParent = []
    imagePaths = []
    volumeNumbers = []
    carrierTypes = []
    
    carriersByType = groupby(carriers, itemgetter(4))
    
    for carrierType, carrierTypeGroup in carriersByType:
        # Set up list to store all Volume Numbers within this type group
        volumeNumbersTypeGroup = []
        for carrier in carrierTypeGroup:
        
            IPIdentifierParent = carrier[colsBatchManifest["PPN"]]
            imagePath = carrier[colsBatchManifest["dirDisc"]]
            volumeNumber = carrier[colsBatchManifest["volumeNo"]]
            carrierType = carrier[colsBatchManifest["carrierType"]]

            # TODO: * validate parent PPN (see above) and/or check existence of corresponding catalog record
            #       * check for relation between IPIdentifier and IPIdentifierParent (if possible / meaningful)
            #       * check IPIdentifierParent against *all other* IPIdentifierParent  values in batch

            # Update lists and check for some obvious errors
                      
            IPIdentifiersParent.append(IPIdentifierParent)
            imagePaths.append(imagePath)
            
            # Check if imagePath is existing directory
            
            # Full path, relative to batchIn TODO: check behaviour on Window$
            imagePathFull = os.path.normpath(os.path.join(batchIn, imagePath)) 
            imagePathAbs = os.path.abspath(imagePathFull)
            
            # Append absolute path to list (used later for completeness check)
            dirsInMetaCarriers.append(imagePathAbs)
            
            if os.path.isdir(imagePathFull) == False:
                errors.append("IP " + IPIdentifier + ": '" + imagePath + \
                "' is not a directory")
                        
            # Create Carrier class instance for this carrier
            thisCarrier = Carrier(IPIdentifier, IPIdentifierParent, imagePathFull, volumeNumber, carrierType)
            fileGrp, divDisc, fileCounter = processCarrier(thisCarrier, fileGrp, dirSIP, fileCounterStart)
            
            # Add to IP class instance
            thisIP.append(thisCarrier)
            
            # Update fileCounterStart # TODO will go wrong b/c not updated now that it lives in this function!!!
            fileCounterStart = fileCounter
                                                          
            # convert volumeNumber to integer (so we can do more checking below)
            try:
                volumeNumbersTypeGroup.append(int(volumeNumber))
            except ValueError:
                # Raises error if volumeNumber string doesn't represent integer
                errors.append("IP " + IPIdentifier + ": '" + volumeNumber + \
                "' is illegal value for 'volumeNumber' (must be integer)") 

            # Check carrierType value against controlled vocabulary 
            if carrierType not in carrierTypeAllowedValues:
                errors.append("IP " + IPIdentifier + ": '" + carrierType + \
                "' is illegal value for 'carrierType'")
            carrierTypes.append(carrierType)

            # Update structmap in METS
            structDivTop.append(divDisc)
  
        # Add volumeNumbersTypeGroup to volumeNumbers list
        volumeNumbers.append(volumeNumbersTypeGroup)           
    
    # Get metadata of IPIdentifierParent from GGC and convert to MODS format
    mdMODS = createMODS(thisIP)
 
    # Append metadata to METS
    xmlData.append(mdMODS) 
     
    if createSIPs == True:
        # Write METS file to SIP directory                                
        metsAsString = etree.tostring(mets, pretty_print=True, encoding="UTF-8")
        metsFname = os.path.join(dirSIP,"mets.xml")
        
        with open(metsFname, "w") as text_file:
            text_file.write(metsAsString)

    # IP-level consistency checks

    # Parent IP identifiers must all be equal 
    if IPIdentifiersParent.count(IPIdentifiersParent[0]) != len(IPIdentifiersParent):
        errors.append("IP " + IPIdentifier + ": multiple values found for 'IPIdentifierParent'")

    # imagePath values must all be unique (no duplicates!)
    uniqueImagePaths = set(imagePaths)
    if len(uniqueImagePaths) != len(imagePaths):
        errors.append("IP " + IPIdentifier + ": duplicate values found for 'imagePath'") 

    # Consistency checks on volumeNumber values within each carrierType group
            
    for volumeNumbersTypeGroup in volumeNumbers:
        # Volume numbers within each carrierType group must be unique
        uniqueVolumeNumbers = set(volumeNumbersTypeGroup)
        if len(uniqueVolumeNumbers) != len(volumeNumbersTypeGroup):
            errors.append("IP " + IPIdentifier + " (" + carrierType + "): duplicate values found for 'volumeNumber'")

        # Report warning if lower value of volumeNumber not equal to '1'
        volumeNumbersTypeGroup.sort()
        if volumeNumbersTypeGroup[0] != 1:
            warnings.append("IP " + IPIdentifier + " (" + carrierType + "): expected '1' as lower value for 'volumeNumber', found '" + \
            str(volumeNumbersTypeGroup[0]) + "'")
        
        # Report warning if volumeNumber does not contain consecutive numbers (indicates either missing 
        # volumes or data entry error)
    
        if sorted(volumeNumbersTypeGroup) != range(min(volumeNumbersTypeGroup), max(volumeNumbersTypeGroup) + 1):
            warnings.append("IP " + IPIdentifier + " (" + carrierType + "): values for 'volumeNumber' are not consecutive")
    
def main():

    # Constants (put in config file later)
        
    # Batch manifest file - basic capture-level metadata about carriers
    fileBatchManifest = "manifest.csv"

    # Header values of mandatory columns in batch manifest
    requiredColsBatchManifest = ['jobID',
                                'PPN',
                                'dirDisc',
                                'volumeNo',
                                'carrierType']
    
    # Controlled vocabulary for 'carrierType' field
    carrierTypeAllowedValues = ['cd-rom',
                                'cd-audio',
                                'dvd-rom',
                                'dvd-video']
                                
    # Define name spaces for METS output
    global mets_ns
    global mods_ns
    global xlink_ns
    global xsi_ns
    global metsSchema
    global modsSchema
    global NSMAP
    mets_ns = 'http://www.loc.gov/METS/'
    mods_ns = 'http://www.loc.gov/mods/v3'
    xlink_ns = 'http://www.w3.org/1999/xlink'
    xsi_ns = 'http://www.w3.org/2001/XMLSchema-instance'
    metsSchema = 'http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd'
    modsSchema = 'http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods-3-4.xsd'
    
    NSMAP =  {"mets" : mets_ns,
         "mods" : mods_ns,
         "xlink" : xlink_ns,
         "xsi": xsi_ns}
       
    # Set up lists for storing errors and warnings
    # Defined as global so we can easily add to them within functions
    global errors
    global warnings
    errors = []
    warnings = []
    
    global out
    global err
       
    # Set encoding of the terminal to UTF-8
    if sys.version.startswith("2"):
        out = codecs.getwriter("UTF-8")(sys.stdout)
        err = codecs.getwriter("UTF-8")(sys.stderr)
    elif sys.version.startswith("3"):
        out = codecs.getwriter("UTF-8")(sys.stdout.buffer)
        err = codecs.getwriter("UTF-8")(sys.stderr.buffer)
    
    # Global flag that indicates if SIPs will be written
    global createSIPs
    createSIPs = False
    
    # Get input from command line
    args = parseCommandLine()
    action = args.subcommand
    batchIn = os.path.normpath(args.batchIn)
   
    if action == "write":
        dirOut = os.path.normpath(args.dirOut)
        createSIPs = True
    else:
        # Dummy value
        dirOut = None
        
        
    # Check if batch dir exists
    if os.path.isdir(batchIn) == False:
        errors.append("input batch directory does not exist")
        errorExit(errors,err)
        
    # Get listing of all directories (not files) in batch dir (used later for completeness check)
    # Note: all entries as full, absolute file paths!
    dirsInBatch = get_immediate_subdirectories(batchIn)
    
    # List for storing directories as extracted from carrier metadata file (see below)
    # Note: all entries as full, absolute file paths!
    dirsInMetaCarriers = [] 
    
    # Check if batch manifest exists
    batchManifest = os.path.normpath(batchIn + "/" + fileBatchManifest)
    if os.path.isfile(batchManifest) == False:
        errors.append("file " + batchManifest + " does not exist")
        errorExit(errors,err)

    # Read batch manifest as CSV and import header and
    # row data to 2 separate lists
    # TODO: make this work in Python 3, see also:
    # http://stackoverflow.com/a/5181085/1209004
    try:
        fBatchManifest = open(batchManifest,"rb")
        batchManifestCSV = csv.reader(fBatchManifest)
        headerBatchManifest = next(batchManifestCSV)
        rowsBatchManifest = [row for row in batchManifestCSV]
        fBatchManifest.close()
    except IOError:
        errors.append("cannot read " + batchManifest)
        errorExit(errors,err)
    except csv.Error:
        errors.append("error parsing " + batchManifest)
        errorExit(errors,err)

    # Remove any empty list elements (e.g. due to EOL chars)
    # to avoid trouble with itemgetter
    for item in rowsBatchManifest:
        if item == []:
            rowsBatchManifest.remove(item)

    # Create output directory if in SIP creation mode
    if createSIPs == True:
        # Remove output dir tree if it exists already
        # Potentially dangerous, so ask for user confirmation 
        if os.path.isdir(dirOut) == True:
        
            out.write("This will overwrite existing directory '" + dirOut + \
            "' and remove its contents!\nDo you really want to proceed (Y/N)? > ")
            response = input()
            
            if response.upper() == "Y":
                try:
                    shutil.rmtree(dirOut)
                except OSError:
                    errors.append("cannot remove '" + dirOut + "'" )
                    errorExit(errors,err)
                
        # Create new dir
        try:
            os.makedirs(dirOut)
        except OSError:
            errors.append("cannot create '" + dirOut + "'" )
            errorExit(errors,err)

    # ********
    # ** Process batch manifest **
    # ******** 

    # Check that there is exactly one occurrence of each mandatory column
 
    for requiredCol in requiredColsBatchManifest:
        occurs = headerBatchManifest.count(requiredCol)
        if occurs != 1:
            errors.append("found " + str(occurs) + " occurrences of column '" + requiredCol + "' in " + \
            batchManifest + " (expected 1)")
            # No point in continuing if we end up here ...
            errorExit(errors,err)

    # Set up dictionary to store header fields and corresponding column numbers
    colsBatchManifest = {}

    col = 0
    for header in headerBatchManifest:
        colsBatchManifest[header] = col
        col += 1

    # Sort rows by IPIdentifier (PPN)
    rowsBatchManifest.sort(key=itemgetter(1))
    
    # Group by IPIdentifier field (PPN)
    metaCarriersByIP = groupby(rowsBatchManifest, itemgetter(1))
    
    # ********
    # ** Iterate over IPs**
    # ******** 

    #processIPs(metaCarriersByIP, dirOut, colsBatchManifest, batchIn, dirsInMetaCarriers, carrierTypeAllowedValues)
    
    for IPIdentifier, carriers in metaCarriersByIP:
        processIP(IPIdentifier, carriers, dirOut, colsBatchManifest, batchIn, dirsInMetaCarriers, carrierTypeAllowedValues)
    
    # Check if directories that are part of batch are all represented in carrier metadata file
    # (reverse already covered by checks above)
    
    # Diff as list
    diffDirs = list(set(dirsInBatch) - set(dirsInMetaCarriers))
    
    # Report each item in list as an error
    
    for directory in diffDirs:
        errors.append("IP " + IPIdentifier + ": directory '" + directory + "' not referenced in '"\
        + batchManifest + "'")
 
    # Output errors and warnings
    err.write("Batch validation yielded " + str(len(errors)) + " errors and " + str(len(warnings)) + " warnings \n" )
    err.write("**** Errors ****\n")
    for error in errors:
        err.write("Error - " + error + "\n")
    err.write("**** Warnings ****\n")    
    for warning in warnings:
        err.write("Warning - " + warning + "\n") 
 

if __name__ == "__main__":
    main()