import logging
import re
import sys


class CachingWriter:
    def __init__(self, name, docache=True):
        self.cache = {}
        self.callcount = 0
        self.writecount = 0
        self.dupsskipped = 0
        self.DELIMITER = "\x07"
        self.QUOTE = "\x01"
        self.MAXSIZE = 30000000  # max size
        self.name = name
        self.fields = 0
        self.docache = docache  # boolean

    def stats(self):
        logging.info("Statistics")
        logging.info(f"{self.name} cache name")
        logging.info(f"{self.callcount} calls")
        logging.info(f"{self.writecount} records written")
        logging.info(f"{self.dupsskipped} records skipped")

    def tsize(self, thing):
        result = 0
        for t in thing:
            result += sys.getsizeof(t)

        return result

    def write(self, data, f):
        self.callcount += 1

        if not self.docache:
            self.writedb(data, f)
            return

        idx = int(data[0])
        this_size = self.tsize(data)

        if idx in self.cache:
            #  check to see if this is larger than last time
            old_size = self.cache[idx]
            if this_size <= old_size:  # if smaller, skip it
                self.dupsskipped += 1
                return

        self.cache[idx] = this_size
        self.writedb(data, f)

    def writedb(self, data, f):
        """write a record the database file"""
        self.writecount += 1
        d = ""
        leftbr = self.QUOTE + "{"
        rightbr = "}" + self.QUOTE

        if self.fields == 0:
            self.fields = len(data)
        else:
            if len(data) != self.fields:
                print("expected", self.fields, "fields but got", len(data))
                print(data)

        for item in data:
            sitem = str(item).replace("\n", " ").rstrip()

            if item is None:  # postgres doesn't like this'
                sitem = ""

            elif isinstance(item, list):  # postgres array is like "{'a', 'b' ... }"
                sitem = re.sub(r"^\[", leftbr, sitem)
                sitem = re.sub(r"\]$", rightbr, sitem)

            d += sitem + self.DELIMITER
        d = d[:-1] + "\n"  # trim delimiter,add newline

        f.write(d)
