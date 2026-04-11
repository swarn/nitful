# `nitful`: The Useful NITF Library

`nitful` is a zero-dependency Python library and command-line utility for
reading, writing, and manipulating National Imagery Transmission Format (NITF /
JBF) files.

> **Status: Alpha.** `nitful` is highly functional, but the API may still
> undergo changes. The library currently parses standard headers and a select
> number of extensions.

**Features**

- **Command-Line Tool:** Inspect, dump, filter, or strip NITF metadata directly
  from the command line.
- **Rich Data Structures:** Headers and extensions are parsed into native,
  nested Python Dataclasses, enabling type-checking and IDE autocompletion.
- **Lazy Loading:** Image data is skipped and can be loaded later, so that
  parsing even massive NITF files has low memory overhead.
- **Read-Modify-Write:** Read an image, modify fields, add TREs/DESs, and
  seamlessly write a new image.
- **Zero Dependencies:** Written in pure Python.

---

## Table of Contents
- [Installation](#installation)
- [Command-Line Usage](#command-line-usage)
- [Python API: Reading Data](#python-api-reading-data)
- [Python API: Manipulating Data](#python-api-manipulating-data)
- [Working with Image Data](#working-with-image-data)
  - [Numpy](#pixels-in-numpy)
  - [Pyvips](#pixels-in-pyvips)
- [Supported Extensions](#supported-extensions)

---


## Installation

`nitful` is available on PyPI and can be installed with standard package
managers.

For library use within a Python project:

```sh
pip install nitful
```

If you strictly want to use `nitful` as a command-line tool, you can install it
with [pipx][pipx]:

```sh
pipx install nitful
```

**Development Installation**
If you want to run the latest unreleased code or contribute to the project, you
can install directly from the repository:
```sh
git clone [https://github.com/swarn/nitful.git](https://github.com/swarn/nitful.git)
cd nitful
pip install -e .
```

[pipx]: https://pipx.pypa.io/stable/


## Command-Line Usage

`nitful` provides a convenient CLI for inspecting and manipulating NITF files.

*(Note: If your environment didn't expose the `nitful` command to your PATH,
you can always execute the tool via `python -m nitful`)*.

### Dump metadata to text

Print the entire file structure to standard output:

```sh
nitful dump image.ntf
```

Filter the output to target specific image segments, Tagged Record Extensions
(TREs), or Data Extension Segments (DESs):

```sh
nitful dump image.ntf --header --image 1 --tre RPC00B --des CSEPHB
```

This is an inclusive filter. The command above will print the file header with
all its TREs, image 1 with all its TREs, any other RPC00B TREs, and all CSEPHB
DESs.


### Strip image payloads

Create a metadata-only copy of a NITF by stripping out the image payloads. This
is useful for sharing files for debugging or metadata analysis:

```sh
nitful strip image.ntf stripped_metadata.ntf
```


## Python API: Reading Data

`nitful` parses the binary headers into type-annotated Python dataclasses.
Image data is not eagerly loaded, so reading large NITF files has low memory
overhead.

```python
import nitful

# Load the file
nitf = nitful.load("tests/data/mock.ntf")

# Access standard file header fields
print(f"File Security: {nitf.security.SCLAS}")
print(f"Number of images: {len(nitf.image_segments)}")


# Assuming there is an ICHIPB TRE in the first image segment.
from nitful.extensions.ichipb import ICHIPB
img = nitf.image_segments[0]
ichipb = next(tre for tre in img.IXSHD if type(tre) is ICHIPB)
print(f"Image scale factor: {ichipb.SCALE_FACTOR}")
```

You can also dig into complex Data Extension Segments (DES):

```python
# In addition to switching on type, you can simply check tags.
csephb = next(des for des in nitf.data_segments if des.DESID == "CSEPHB")

# Type casting isn't necessary, but will provide your IDE or LSP with useful
# information.
from nitful.extensions.csephb import CSEPHB
from typing import cast
csephb = cast(CSEPHB, csephb)

print(f"Ephemeris date: {csephb.DATE_EPHEM}")
print(f"First ephemeris Vector: {csephb.ephemerides[0]}")
```


## Python API: Manipulating Data

Read-modify-write workflows are easy:

```python
import nitful
from nitful.core.common import SecurityClass
from nitful.extensions.csephb import CSEPHB

nitf = nitful.load("tests/data/mock.ntf")

# Modify a basic header field.
nitf.security.SCLAS = SecurityClass.TOPSECRET

# Change the X coordinate of the first ephemeris point in CSEPHB.
csephb = next(des for des in nitf.data_segments if type(des) is CSEPHB)
csephb.ephemerides[0][0] += 10.5

# Save the new file. This will efficiently stream the pixel data from the
# original to the new image.
nitful.save(nitf, "modified.ntf")
```

## Working with Image Data

`nitful` avoids dependencies like `numpy` or `pyvips`, but can work with them.

By default, `nitful` skips reading pixel data, but makes it available via the
`DeferredImageData` class. You can read the pixels as raw bytes, but it's
usually more useful to use a library.

*All examples below assume you've loaded a NITF file with at least one image
segment.*

```python
import nitful
from nitful.core.spec import DeferredImageData
from typing import cast

nitf = nitful.load('image.ntf')
segment = nitf.image_segments[0]

# Casting is not strictly necessary here, but prevents warnings from your
# type checker. nitful always assigns DeferredImageData on read, but allows
# you to assign raw bytes.
data = cast(DeferredImageData, segment.data)
```

### Pixels in Numpy

If the image is uncompressed, you can use `numpy.memmap` to map the disk bytes
directly into an array.

```python
import numpy as np

pixels = np.memmap(
    'image.ntf',        # or data.path
    dtype=np.uint8,     # adjust based on segment.ABPP
    mode='r',
    offset=data.offset,
    shape=(segment.NROWS, segment.NCOLS)
)

# Numpy only reads the data necessary, not the whole image.
print(np.mean(pixels[:100, :100]))
```

### Pixels in pyvips

`pyvips` is a good library for handling large and/or compressed images:

```python
import pyvips

with open('image.ntf', 'rb') as f:
    f.seek(data.offset)

    source = pyvips.SourceCustom(f)
    image = pyvips.Image.new_from_source(source, "", access="sequential")

    # Create a thumbnail image. Pyvips intelligently streams the pixel data,
    # so the memory overhead is typically much smaller than the full image.
    image.thumbnail_image(512).write_to_file("preview.jpg")
```

### Pixels as bytes

You can also get the pixel data as raw bytes. Note that this reads the entire
image into memory!

```python
raw_bytes = data.read()
```

You can set pixels to raw bytes, as well:

```python
pixels = b'1234'
nitf.image_segments[0].data = pixels
nitful.save(nitf, 'new_file.ntf')
```

*Note: It is up to you to correctly configure the image segment metadata (NROWS, ABPP, etc.) when modifying pixel data.*


## Supported Extensions

The list of explicitly supported SDEs is small but growing; see the `nitful/extensions` directory.

Crucially, an extension does not need to be supported by `nitful` for you to
read or modify the rest of the file. Unknown extensions are safely preserved as
raw bytes and written back out identically.