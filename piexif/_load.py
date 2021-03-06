import struct

from ._common import *
from ._exif import *


LITTLE_ENDIAN = b"\x49\x49"


def load(input_data):
    """
    py:function:: piexif.load(filename)

    Return exif data as dict. Keys(IFD name), be contained, are "0th", "Exif", "GPS", "Interop", "1st", and "thumbnail". Without "thumbnail", the value is dict(tag name/tag value). "thumbnail" value is JPEG as bytes.

    :param str filename: JPEG or TIFF
    :return: Exif data({"0th":dict, "Exif":dict, "GPS":dict, "Interop":dict, "1st":dict, "thumbnail":bytes})
    :rtype: dict
    """
    exif_dict = {"0th":{},
                 "Exif":{},
                 "GPS":{},
                 "Interop":{},
                 "1st":{},
                 "thumbnail":None}
    exifReader = _ExifReader(input_data)
    if exifReader.tiftag is None:
        return exif_dict

    if exifReader.tiftag[0:2] == LITTLE_ENDIAN:
        exifReader.endian_mark = "<"
    else:
        exifReader.endian_mark = ">"

    pointer = struct.unpack(exifReader.endian_mark + "L",
                            exifReader.tiftag[4:8])[0]
    exif_dict["0th"] = exifReader.get_ifd_dict(pointer, "0th")
    first_ifd_pointer = exif_dict["0th"].pop("first_ifd_pointer")
    if 34665 in exif_dict["0th"]:
        pointer = exif_dict["0th"][34665]
        exif_dict["Exif"] = exifReader.get_ifd_dict(pointer, "Exif")
    if 34853 in exif_dict["0th"]:
        pointer = exif_dict["0th"][34853]
        exif_dict["GPS"] = exifReader.get_ifd_dict(pointer, "GPS")
    if 40965 in exif_dict["Exif"]:
        pointer = exif_dict["Exif"][40965]
        exif_dict["Interop"] = exifReader.get_ifd_dict(pointer, "Interop")
    if first_ifd_pointer != b"\x00\x00\x00\x00":
        pointer = struct.unpack(exifReader.endian_mark + "L",
                                first_ifd_pointer)[0]
        exif_dict["1st"] = exifReader.get_ifd_dict(pointer, "1st")
        if (513 in exif_dict["1st"]) and (514 in exif_dict["1st"]):
            end = exif_dict["1st"][513]+exif_dict["1st"][514]
            thumb = exifReader.tiftag[exif_dict["1st"][513]:end]
            exif_dict["thumbnail"] = thumb
    return exif_dict


class _ExifReader(object):
    def __init__(self, data):
        if data[0:2] == b"\xff\xd8":  # JPEG
            segments = split_into_segments(data)
            app1 = get_app1(segments)
            if app1:
                self.tiftag = app1[10:]
            else:
                self.tiftag = None
        elif data[0:2] in (b"\x49\x49", b"\x4d\x4d"):  # TIFF
            self.tiftag = data
        elif data[0:4] == b"Exif":  # Exif
            self.tiftag = data[6:]
        elif data[-4:].lower() in (".jpg", "jpeg", ".jpe", ".tif", "tiff"):
            with open(data, 'rb') as f:
                data = f.read()
            if data[0:2] == b"\xff\xd8":  # JPEG
                segments = split_into_segments(data)
                app1 = get_app1(segments)
                if app1:
                    self.tiftag = app1[10:]
                else:
                    self.tiftag = None
            elif data[0:2] in (b"\x49\x49", b"\x4d4d"):  # TIFF
                self.tiftag = data
            else:
                raise ValueError("Given file is neither JPEG nor TIFF.")
        else:
            raise ValueError("Given file is neither JPEG nor TIFF.")

    def get_ifd_dict(self, pointer, ifd_name, read_unknown=False):
        ifd_dict = {}
        tag_count = struct.unpack(self.endian_mark + "H",
                                  self.tiftag[pointer: pointer+2])[0]
        offset = pointer + 2
        if ifd_name in ["0th", "1st"]:
            t = "Image"
        else:
            t = ifd_name
        p_and_value = []
        for x in range(tag_count):
            pointer = offset + 12 * x
            tag = struct.unpack(self.endian_mark + "H",
                       self.tiftag[pointer: pointer+2])[0]
            value_type = struct.unpack(self.endian_mark + "H",
                         self.tiftag[pointer + 2: pointer + 4])[0]
            value_num = struct.unpack(self.endian_mark + "L",
                                      self.tiftag[pointer + 4: pointer + 8]
                                      )[0]
            value = self.tiftag[pointer+8: pointer+12]
            p_and_value.append((pointer, value_type, value_num, value))
            v_set = (value_type, value_num, value, tag)
            if tag in TAGS[t]:
                ifd_dict[tag] = self.convert_value(v_set)
            elif read_unknown:
                ifd_dict[tag] = (v_set[0], v_set[1], v_set[2], self.tiftag)
            #else:
            #    pass

        if ifd_name == "0th":
            pointer = offset + 12 * tag_count
            ifd_dict["first_ifd_pointer"] = self.tiftag[pointer:pointer + 4]
        return ifd_dict

    def convert_value(self, val):
        data = None
        t = val[0]
        length = val[1]
        value = val[2]

        if t == 1: # BYTE
            if length > 4:
                pointer = struct.unpack(self.endian_mark + "L", value)[0]
                data = struct.unpack("B" * length,
                                     self.tiftag[pointer: pointer + length])
            else:
                data = struct.unpack("B" * length, value[0:length])
        elif t == 2: # ASCII
            if length > 4:
                pointer = struct.unpack(self.endian_mark + "L", value)[0]
                data = self.tiftag[pointer: pointer+length - 1]
            else:
                data = value[0: length - 1]
        elif t == 3: # SHORT
            if length > 2:
                pointer = struct.unpack(self.endian_mark + "L", value)[0]
                data = struct.unpack(self.endian_mark + "H" * length,
                                     self.tiftag[pointer: pointer+length*2])
            else:
                data = struct.unpack(self.endian_mark + "H" * length,
                                     value[0:length * 2])
        elif t == 4: # LONG
            if length > 1:
                pointer = struct.unpack(self.endian_mark + "L", value)[0]
                data = struct.unpack(self.endian_mark + "L" * length,
                                     self.tiftag[pointer: pointer+length*4])
            else:
                data = struct.unpack(self.endian_mark + "L" * length,
                                     value)
        elif t == 5: # RATIONAL
            pointer = struct.unpack(self.endian_mark + "L", value)[0]
            if length > 1:
                data = tuple(
                    (struct.unpack(self.endian_mark + "L",
                                   self.tiftag[pointer + x * 8:
                                       pointer + 4 + x * 8])[0],
                     struct.unpack(self.endian_mark + "L",
                                   self.tiftag[pointer + 4 + x * 8:
                                       pointer + 8 + x * 8])[0])
                    for x in range(length)
                )
            else:
                data = (struct.unpack(self.endian_mark + "L",
                                      self.tiftag[pointer: pointer + 4])[0],
                        struct.unpack(self.endian_mark + "L",
                                      self.tiftag[pointer + 4: pointer + 8]
                                      )[0])
        elif t == 7: # UNDEFINED BYTES
            if length > 4:
                pointer = struct.unpack(self.endian_mark + "L", value)[0]
                data = self.tiftag[pointer: pointer+length]
            else:
                data = value[0:length]
#        elif t == 9: # SLONG
#            if length > 1:
#                pointer = struct.unpack(self.endian_mark + "L", value)[0]
#                data = struct.unpack(self.endian_mark + "l" * length,
#                                     self.exif_str[pointer: pointer+length*4])
#            else:
#                data = struct.unpack(self.endian_mark + "l" * length,
#                                     value)
        elif t == 10: # SRATIONAL
            pointer = struct.unpack(self.endian_mark + "L", value)[0]
            if length > 1:
                data = tuple(
                  (struct.unpack(self.endian_mark + "l",
                   self.tiftag[pointer + x * 8: pointer + 4 + x * 8])[0],
                   struct.unpack(self.endian_mark + "l",
                   self.tiftag[pointer + 4 + x * 8: pointer + 8 + x * 8])[0])
                  for x in range(length)
                )
            else:
                data = (struct.unpack(self.endian_mark + "l",
                                      self.tiftag[pointer: pointer + 4])[0],
                        struct.unpack(self.endian_mark + "l",
                                      self.tiftag[pointer + 4: pointer + 8]
                                      )[0])
        else:
            raise ValueError("Exif might be wrong. Got incorrect value " +
                             "type to decode.\n" +
                             "tag: " + str(val[3]) + "\ntype: " + str(t))

        if isinstance(data, tuple) and (len(data) == 1):
            return data[0]
        else:
            return data
