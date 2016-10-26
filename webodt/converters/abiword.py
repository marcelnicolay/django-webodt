# -*- coding: utf-8 -*-
from webodt import Document
from webodt.conf import WEBODT_ABIWORD_COMMAND
from webodt.converters import ODFConverter
from webodt.helpers import guess_format_and_filename
import subprocess


class AbiwordODFConverter(ODFConverter):


    def convert(self, document, format=None, output_filename=None, delete_on_close=True):
        output_filename, format = guess_format_and_filename(output_filename, format)
        process = subprocess.Popen(WEBODT_ABIWORD_COMMAND,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        args = (document.name, output_filename, format)
        process.communicate(b'convert %s %s %s\n' % args)
        fd = Document(output_filename, mode='r', delete_on_close=delete_on_close)
        return fd
