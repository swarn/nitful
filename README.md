# BIIF

Reading and writing NITF (aka Joint BIIF Profile) files with pure Python and no
dependencies.

Very much a work in progress.



## Intallation

You can install locally with pip:
``` sh
git clone ...
cd biif
pip install -e .
```


## Usage

Read a file and inspect values as structured data:
``` pycon
>>> import biif
>>> nitf = biif.load("path/to/file.ntf")
>>> nitf.FHDR
NITF
>>> nitf.FVER
02.10
>>> len(nitf.image_segments)
1
>>> nitf.image_segments[0].IREP
MONO
>>> type(nitf.data_segments[2])
<class 'biif.models.extensions.csephb.CSEPHB'>
>>> nitf.data_segments[2].ephemerides[0]
[-2370745.44, -3762357.23, 4863859.91]
>>> biif.dump(nitf)
======================= FILE HEADER ========================
FHDR: 'NITF'
FVER: '02.10'
CLEVEL: '09'
STYPE: 'BF01'
OSTAID: 'GPSM      '
FDT: '20260313163302'
...
```
