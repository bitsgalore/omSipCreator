
## About

OmSipCreator is a tool for converting batches of disk images (e.g. ISO 9660 CD-ROM images, raw floppy disk images, but also ripped audio files)  into SIPs that are ready for ingest in an archival system. This includes automatic generation of METS metadata files with structural and bibliographic metadata. Bibliographic metadata are extracted from the KB general catalogue, and converted to MODS format. OmSipCreator also performs various quality checks on the input batches. Finally, it can be used to remove erroneous entries from a batch.

## Notes and warnings

At the moment this software is still a somewhat experimental proof-of-concept that hasn't had much testing at this stage. Neither the current batch input format nor the SIP output format (including METS metadata) have  been finalised yet, and may be subject to further changes. 
 
Also, the (bibliographic) metadata component is specific to the situation and infrastructure at the KB, although it could easily be adapted to other infrastructures. To do this you would need to customize the *createMODS* function.

## Dependencies

OmSipCreator was developed and tested under Python 3.6. It may (but is not guaranteed to) work under Python 2.7 as well. If you run it under Linux you need to install (a recent version of) [*MediaInfo*](https://mediaarea.net/en/MediaInfo). Installation instructions can be found [here](https://mediaarea.net/en/MediaInfo/Download/Ubuntu). OmSipCreator expects that the *mediainfo* binary is located under *usr/bin* (which is the default installation location when installing from a Debian package). A Windows version of *MediaInfo* is already included with OmSipCreator.

## Installation

The recommended way to install omSipCreator is to use [pip](https://en.wikipedia.org/wiki/Pip_(package_manager)). The following command will install omSipCreator and its dependencies: 

    pip install omSipCreator

## Usage

OmSipCreator has three sub-commands:

* *verify* - verifies a batch without writing any output
* *write* - transforms the contents  of a batch into ingest-ready [SIPs](http://www.iasa-web.org/tc04/submission-information-package-sip)
* *prune* - creates a sanitised version of a batch with errors. For each carrier in a bath that has errors, it will copy the data of all carriers that belong to its respective PPN to an 'error batch'. The carriers are subsequently removed from the input batch (including the batch manifest). After this operation the input batch will be error-free (and ready for further processing with the *write* subcommand).

### Verify a batch without writing any SIPs

    omSipCreator verify batchIn

Here *batchIn* is the batch directory.

### Create a sanitised version of a batch
 
    omSipCreator prune batchIn batchErr

Here *batchErr* is the name of the batch that will contain all PPNs that have problems. If *batchErr* is an existing directory, *all* of its contents will be overwritten! OmSipCreator will prompt you for confirmation if this happens:

    This will overwrite existing directory 'failed' and remove its contents!
    Do you really want to proceed (Y/N)? >

### Verify a batch and write SIPs

    omSipCreator write batchIn dirOut

Here *dirOut* is the directory where the SIPs will be created. If *dirOut* is an existing directory, *all* of its contents will be overwritten! OmSipCreator will prompt you for confirmation if this happens:

    This will overwrite existing directory 'sipsOut' and remove its contents!
    Do you really want to proceed (Y/N)? > 

### How to use the verify, prune and write commands

The important thing is that any errors in the input batch are likely to result in SIP output that is either unexpected or just plain wrong. So *always* verify each batch first, and fix any errors if necessary. The 


1. Always first run omSipCreator in *verify* mode.
2. If this results in any reported errors, fix them by running in *prune* mode.
3. Double-check the sanitised batch by running in *verify* mode once more.
4. Once no errors are reported, create the SIPs by running in *write* mode.
5. Finally, fix any 'error' batches that were generated by the *prune* command (this may involve manual processing/editing), verify them and then create the SIPs by running in *write* mode.

<!-- TODO: a flowchart would be nice here! -->


## Structure of input batch

The input batch is simply a directory that contains a number of subdirectories, each of which represents exactly one data carrier. Furthermore it contains a *batch manifest*, which is a comma-delimited text file with basic metadata about each carrier. The diagram below shows an example of a batch that contains 3 carriers.


    ├── manifest.csv
    ├── 1628c634-edeb-11e6-a9c8-00237d497a29
    │   ├── track01.cdda.wav
    │   ├── track02.cdda.wav
    │   ├── ...
    │   ├── ...
    │   ├── track13.cdda.wav
    │   └── checksums.sha512
    ├── 29c586b4-edeb-11e6-9a83-00237d497a29
    │   ├── image1.iso
    │   └── checksums.sha512
    └── ceaf9bf6-edfb-11e6-9c13-00237d497a29
        ├── image2.iso
        └── checksums.sha512

## Carrier directory structure

Each carrier directory contains:

1. One or more files that represent the data carrier. This is typically an ISO 9660 image, but for an audio CD with multiple tracks this can also be multiple audio (e.g. WAV) files. In the latter case, it is important that the original playing order can be inferred from the file names. In other words, sorting the file names in ascending order should reproduce the original playing order. Note that (nearly?) all audio CD ripping software does this by default.
2. Exactly one checksum file that contains the SHA-512 checksums of all files in the directory. The name of the checksum file must end with the extension *.sha512* (other than that its name doesn't matter). Each line in the file has the following format:

        checksum filename

    Both fields are separated by 1 or more spaces. the *filename* field must not include any file path information. Here's an example:

        6bc4f0a53e9d866b751beff5d465f5b86a8a160d388032c079527a9cb7cabef430617f156abec03ff5a6897474ac2d31c573845d1bb99e2d02ca951da8eb2d01 01.flac
        ae6d9b5d47ecc34345bdbf5a0c45893e88b5ae4bb2927a8f053debdcd15d035827f8b81a97d3ee4c4ace5257c4cc0cde13b37ac816186e84c17b94c9a04a1608 02.flac
        ::
        ::
        49b0a0d2f40d9ca1d7201cb544e09d69f1162dd8a846c2c3d257e71bc28643c015d7bc458ca693ee69d5db528fb2406021ed0142f26a423c6fb4f115d3fa58e7 20.flac
        d9fa0b5df358a1ad035a9c5dbb3a882f1286f204ee1f405e9d819862c00590b1d11985c5e80d0004b412901a5068792cd48e341ebb4fe35e360c3eeec33a1f23 cd-info.log
        fa8898fc1c8fe047c1b45975fd55ef6301cfdfe28d59a1e3f785aa3052795cad7a9eff5ce6658207764c52fa9d5cf16808b0fc1cfe91f8c866586e37f0b47d08 dbpoweramp.log
        783ae6ac53eba33b8ab04363e1159a71a38d2db2f8004716a1dc6c4e11581b4311145f07834181cd7ec77cd7199377286ceb5c3506f0630939112ae1d55e3d47 ELL2.iso
        31bca02094eb78126a517b206a88c73cfa9ec6f704c7030d18212cace820f025f00bf0ea68dbf3f3a5436ca63b53bf7bf80ad8d5de7d8359d0b7fed9dbc3ab99 isobuster.log

## Batch manifest format

The batch manifest is a comma-delimited text file with the name *manifest.csv*. The first line is a header line: 

    jobID,PPN,volumeNo,carrierType,title,volumeID,success,containsAudio,containsData, cdExtra

Each of the remaining lines represents one carrier, for which it contains the following fields:

1. *jobID* - internal carrier-level identifier (in our case this is generated by our [*iromlab*](https://github.com/KBNLresearch/iromlab) software). The image file(s) of this carrier are stored in an eponymous directory within the batch.
2. *PPN* - identifier to  physical item in the KB Collection to which this carrier belongs. For the KB case this is the PPN identifier in the KB catalogue.
3. *volumeNo* - for PPNs that span multiple carriers, this defines the volume number (1 for single-volume items). Values must be unique within each *carrierType* (see below)
4. *carrierType* - code that specifies the carrier type. Currently the following values are permitted:
    - cd-rom
    - dvd-rom
    - cd-audio
    - dvd-video
5. *title* - text string with the title of the carrier (or the publication is is part of). Not used by omSipCreator.
6. *volumeID* - text string, extracted from Primary Volume descriptor, empty if cd-audio. Not used by omSipCreator.
7. *success* - True/False flag that indicates status of *iromlab*'s imaging process.
8. *containsAudio* - True/False flag that indicates the carrier contains audio tracks (detected by cd-info)
9. *containsData* - True/False flag that indicates the carrier contains data tracks (detected by cd-info)
10. *cdExtra* - True/False flag that indicates the carrier is an 'enhanced' CD with both audio and data tracks that are located in separate sessions (detected by cd-info)

Below is a simple example of manifest file:

    jobID,PPN,volumeNo,carrierType,title,volumeID,success,containsAudio,containsData,cdExtra
    1628c634-edeb-11e6-a9c8-00237d497a29,121274306,cd-audio,(Bijna) alles over bestandsformaten,Handbook,True,True,False,False
    29c586b4-edeb-11e6-9a83-00237d497a29,155658050,1,cd-rom,(Bijna) alles over bestandsformaten,Handbook,True,False,True,False
    ceaf9bf6-edfb-11e6-9c13-00237d497a29,236599380,1,cd-rom,(Bijna) alles over bestandsformaten,Handbook,True,False,True,False
    b97d56f6-edfb-11e6-8311-00237d497a29,308684745,2,cd-rom,(Bijna) alles over bestandsformaten,Handbook,True,False,True,False

In the above example the second and fourth carriers are both part of a 2-volume item. Consequently the *PPN* values of both carriers are identical.

## SIP structure

Each SIP is represented as a directory. Each carrier that is part of the SIP is represented as a subdirectory within that directory. The SIP's root directory contains a [METS](https://www.loc.gov/mets/) file with technical, structural and bibliographic metadata. Bibliographic metadata is stored in [MODS](https://www.loc.gov/standards/mods/) format (3.4) which is embedded in a METS *mdWrap* element. Here's a simple example of a SIP that is made up of 2 carriers (which are represented as ISO 9660 images):
  

    ── 269448861
       ├── cd-rom
       │   ├── 1
       │   │   └── nuvoorstraks1.iso
       │   └── 2
       │       └── nuvoorstraks2.iso
       └── mets.xml

And here's an example of a SIP that contains 1 audio CD, with separate tracks represented as WAV files:

    ── 16385100X
       ├── cd-audio
       │   └── 1
       │       ├── track01.cdda.wav
       │       ├── track02.cdda.wav
       │       ├── track03.cdda.wav
       │       ├── track04.cdda.wav
       │       ├── track05.cdda.wav
       │       ├── track06.cdda.wav
       │       ├── track07.cdda.wav
       │       ├── track08.cdda.wav
       │       ├── track09.cdda.wav
       │       ├── track10.cdda.wav
       │       ├── track11.cdda.wav
       │       ├── track12.cdda.wav
       │       └── track13.cdda.wav
       └── mets.xml

## METS metadata

### dmdSec

- Contains top-level *mdWrap* element with the following attributes:
    - *MDTYPE* - indicates type of metadata that this element wraps. Value is *MODS*
    - *MDTYPEVERSION* - MODS version, is *3.4* (as per KB Metatadata policies)
- The *mdWrap* element contains one *xmlData* element
- The *xmlData* element contains one *mods* element.

The *mods* element contains the actual metadata elements. Most of these are imported from the KB catalogue record. Since the catalogue use Dublin Core (with some custom extensions), the DC elements are mapped to equivalent MODS elements. The mapping largely follows the [*Dublin Core Metadata Element Set Mapping to MODS Version 3*](http://www.loc.gov/standards/mods/dcsimple-mods.html) by Library of Congress. The table below shows each MODS element with its corresponding data source:

|MODS|Source|
|:--|:--|
|`titleInfo/title`|`dc:title@xsi:type="dcx:maintitle"` (catalogue)|
|`titleInfo/title`|`dc:title` (catalogue)|
|`name/namePart`; `name/role/roleTerm/@type="creator"`|`dc:creator` (catalogue)|
|`name/namePart`; `name/role/roleTerm/@type="contributor"`|`dc:contributor` (catalogue)|
|`originInfo@displayLabel="publisher"/publisher`|`dc:publisher` (catalogue)| 
|`originInfo/dateIssued`|`dc:date` (catalogue)|
|`subject/topic`|`dc:subject` (catalogue)|
|`typeOfResource`|mapping with *carrierType* (carrier metadata file)|
|`note`|`dcx:annotation` (catalogue)|
|`relatedItem/@type="host"/identifier/@type="ppn"`|*PPNParent* (carrier metadata file)|
|`relatedItem/@type="host"/identifier/@type="uri"`|`dc:identifier/@xsi:type="dcterms:URI"`(catalogue)|
|`relatedItem/@type="host"/identifier/@type="isbn"`|`dc:identifier/@xsi:type="dcterms:ISBN"` (catalogue)|

<!-- |`relatedItem/@type="host"/identifier/@type="uri"`|`dcx:recordIdentifier/@xsi:type="dcterms:URI"` (catalogue)| -->

Some additional notes to the above:

- Some of these elements (e.g. *creator* and *contributor*) may be repeatable.
- Title info in KB catalogue can either be in `dc:title@xsi:type="dcx:maintitle"`, `dc:title`, or both. If available,  `dc:title@xsi:type="dcx:maintitle"` is used as the mapping  source; otherwise  `dc:title` is used.
- The *relatedItem* element (with attribute *type* set to *host*) describes the relation of the intellectual entity with its (physical) parent item. It does this by referring to its identifiers in the KB catalogue.

### fileSec

- Contains one top-level *fileGrp* element (if a SIP spans multiple carriers, they are all wrapped inside the same *fileGrp* element).
- The *fileGrp* elements contains 1 or more *file* elements. Each *file* element has the following attributes:
    - *ID* - file identifier (e.g. *FILE_001*, *FILE_002*, etc.)
    - *SIZE* - file size in bytes
    - *MIMETYPE* - Mime type (e.g. *application/x-iso9660*)
    - *CHECKSUM*
    - *CHECKSUMTYPE* (*SHA-512*)
- Each *file* element contains an *FLocat* element with the following attributes:
    - *LOCTYPE* - Locator type. Value is *URL*
    - *xlink:href* - URL of file. Format: filepath, relative to root of SIP directory. Example:
        `xlink:href="file:///cd-rom/4/alles_over_bestandsformaten.iso"`

### structMap

- *structMap* contains a top-level *div* element with the following attributes:
    - *TYPE* - value *physical*
    - *LABEL* - value *volumes*
- Each carrier is wrapped into a *div* element that descibes the carrier using the following attributes:
    - *TYPE* - describes the carrier type. Possible values: *cd-rom*, *cd-audio*, *dvd-rom*, *dvd-video*
    - *ORDER* - in case of multiple carriers, this describes -for each *TYPE*, see above- the order of each volume 
- Each of the above *div* elements contains one or more further *div* elements that describe the components (files) that make up a carrier. They have the following attributes:
    - *TYPE* - describes the nature of the carrier component. Possible values are *disk image* and *audio track*.
    - *ORDER* - describes the order of each component (e.g. for an audio CD that is represented as multiple audio files, it describes the playing order).
- Finally each of the the above (file-level) *div* elements contains one *fptr*. It contains one *FILEID* attribute, whose value corresponds to the corresponding *ID* attribute in the *file* element (see *FileSec* description above).

## Quality checks

When run in either *verify* or *write* mode, omSipCreator performs a number checks on the input batch. Each of he following checks will result in an *error* in case of failure:

- Does the batch directory exist?
- Does the batch manifest exist?
- Can the batch manifest be opened and is it parsable?
- Does the batch manifest contain exactly 1 instance of each mandatory column?
- Does each *jobID* entry point to an existing directory?
- Is each *volumeNumber* entry an integer value?
- Is each *carrierType* entry a permitted value (check against controlled vocabulary)?
- Is each *carrierType* entry consistent with the values of *containsAudio* and *containsData*?
- Is the value of the *success* flag 'True'?
- Are all values of *jobID* within the batch manifest unique (no duplicate values)?
- Are all instances of *volumeNumber* within each *carrierType* group unique?
- Are all directories within the batch referenced in the batch manifest (by way of *jobID*)?
- Does each carrier directory (i.e. *jobID*) contain exactly 1 SHA-512 checksum file (identified by *.sha512* file extension)?
- Does each carrier directory (i.e. *jobID*) contain any files?
- For each entry in the checksum file, is the SHA-512 checksum identical to the re-calculated checksum for that file?
- Does a carrier directory contain any files that are not referenced in the checksum file?
- Does a search for *PPN* in the KB catalogue result in exactly 1 matching record?

In *write* mode omSipCreator performs the following additional checks:

- Is the output directory a writable location?
- Could a SIP directory be created for the current PPN?
- Could a carrier directory be created for the current carrier?
- Could the image file(s) for the current carrier be copied to its SIP carrier directory?
- Does the SHA-512 checksum of each copied image file match the original checksum (post-copy checksum verification)?

Finally, omSipcreator will report a *warning* in the following situations:

- Lower value of *volumeNumber* within a *carrierType* group is not equal to 1.
- Values of *volumeNumber* within a *carrierType* group are not consecutive numbers.

Both situations may indicate a data entry error, but they may also reflect that the physical carriers are simply missing.

<!-- TODO elaborate a bit on difference between FATAL, ERROR and WARNING messages in output -->

## Contributors

Written by Johan van der Knijff, except *sru.py* which was adapted from the [KB Python API](https://github.com/KBNLresearch/KB-python-API) which is written by WillemJan Faber. The KB Python API is released under the GNU GENERAL PUBLIC LICENSE.


## License

OmSipCreator is released under the Apache License 2.0. The KB Python API is released under the GNU GENERAL PUBLIC LICENSE. MediaInfo is released under the BSD 2-Clause License; Copyright (c) 2002-2017, MediaArea.net SARL. All rights reserved. See the `tools/mediainfo` directory for the license statement of MediaInfo.
