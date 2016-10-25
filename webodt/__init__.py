# -*- coding: utf-8 -*-
"""
Whereas Django Templates accept string as template source, there is
inconvenient way of working with ODF template, because ODF work with a
relatively complex structure and it's easier to pass just template_name.

ODFTemplate accepts both packed (regular) or unpacked .odt documents as
templates. Unpacked ODFTemplate is nothing more than just unzipped .odt file.
"""
import os
import zipfile
import tempfile
import shutil
import time
from lxml import etree
from io import StringIO
from django.template import Template
from django.utils.encoding import smart_str
from webodt.conf import WEBODT_TEMPLATE_PATH, WEBODT_ODF_TEMPLATE_PREPROCESSORS, WEBODT_TMP_DIR
from webodt.preprocessors import list_preprocessors


class HTMLTemplate(object):
    """ HTML template class """
    format = 'html'
    content_type = 'text/html'

    def __init__(self, template_name):
        """ Create object by the template name. The template name is relative
        to ``WEBODT_TEMPLATE_PATH`` directory. """
        self.template_name = template_name
        self.template_path = os.path.join(WEBODT_TEMPLATE_PATH, template_name)
        if not os.path.isfile(self.template_path):
            raise ValueError('Template %s not found in directory %s' % (template_name, WEBODT_TEMPLATE_PATH))

    def get_content(self):
        fd = open(self.template_path, 'r')
        content = fd.read()
        fd.close()
        return content

    def render(self, context, delete_on_close=True):
        """ Return rendered HTML (webodt.HTMLDocument instance) """
        # get rendered content
        template = Template(self.get_content())
        content = template.render(context)
        # create and return .html file
        lowlevel_fd, tmpfile = tempfile.mkstemp(suffix='.html', dir=WEBODT_TMP_DIR)
        os.close(lowlevel_fd)
        fd = open(tmpfile, 'w')
        fd.write(smart_str(content))
        fd.close()
        # return HTML document
        return HTMLDocument(tmpfile, delete_on_close=delete_on_close)


class ODFTemplate(object):
    """
    ODF template class
    """

    format = 'odt'
    content_type = 'application/vnd.oasis.opendocument.text'
    _fake_timestamp = time.mktime((2010,1,1,0,0,0,0,0,0))

    def __init__(self, template_name, preprocessors=None):
        """ Create object by the template name. The template name is relative
        to ``WEBODT_TEMPLATE_PATH`` directory.

        template_name: name of the template to load and handle
        """
        if not preprocessors:
            preprocessors = WEBODT_ODF_TEMPLATE_PREPROCESSORS
        self.preprocessors = preprocessors
        self.template_name = template_name
        self.template_path = os.path.join(WEBODT_TEMPLATE_PATH, template_name)
        if os.path.isfile(self.template_path):
            self.packed = True
            self.handler = _PackedODFHandler(self.template_path)
        elif os.path.isdir(self.template_path):
            self.packed = False
            self.handler = _UnpackedODFHandler(self.template_path)
        else:
            raise ValueError('Template %s not found in directory %s' % (template_name, WEBODT_TEMPLATE_PATH))

    def get_content_xml(self):
        """ Return the content.xml file contents """
        return self.handler.get_content_xml()

    def get_meta_xml(self):
        """ Return the meta.xml file contents """
        return self.handler.get_meta_xml()

    def get_styles_xml(self):
        """ Return the styles.xml file contents """
        return self.handler.get_styles_xml()

    def get_file(self,path):
        return self.handler.get_file(path)

    def get_files_to_process(self):
        #parse manifest
        paths = []
        manifest = self.get_file("META-INF/manifest.xml")
        manifest_stream = StringIO(manifest)
        print(manifest_stream.getvalue())
        ee = etree.parse(manifest_stream.getvalue())
        for xml_ref in ee.findall("//{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}file-entry[@{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}media-type='text/xml']"):
            paths.append(xml_ref.attrib['{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}full-path'])
        return paths

    def render(self, context, delete_on_close=True):
        """ Return rendered ODF (webodt.ODFDocument instance)"""
        # create temp output directory
        tmpdir = tempfile.mkdtemp()
        self.handler.unpack(tmpdir)
        # store updated content.xml
        for f_to_process in self.get_files_to_process():
            template = self.get_file(f_to_process)
            for preprocess_func in list_preprocessors(self.preprocessors):
                template = preprocess_func(template)
            template = Template(template)
            xml_result = template.render(context)
            filename = os.path.join(tmpdir, f_to_process)
            result_fd = open(filename, 'w')
            result_fd.write(smart_str(xml_result))
            result_fd.close()

        lowlevel_fd, tmpfile = tempfile.mkstemp(suffix='.odt', dir=WEBODT_TMP_DIR)
        os.close(lowlevel_fd)
        tmpzipfile = zipfile.ZipFile(tmpfile, 'w')
        for root, _, files in os.walk(tmpdir):
            for fn in files:
                path = os.path.join(root, fn)
                os.utime(path, (self._fake_timestamp, self._fake_timestamp))
                fn = os.path.relpath(path, tmpdir)
                tmpzipfile.write(path, fn)
        tmpzipfile.close()
        # remove directory tree
        shutil.rmtree(tmpdir)
        # return ODF document
        return ODFDocument(tmpfile, delete_on_close=delete_on_close)


class _PackedODFHandler(object):

    def __init__(self, filename):
        self.filename = filename

    def get_content_xml(self):
        fd = zipfile.ZipFile(self.filename)
        data = fd.read('content.xml')
        fd.close()
        return data

    def get_meta_xml(self):
        fd = zipfile.ZipFile(self.filename)
        data = fd.read('meta.xml')
        fd.close()
        return data

    def get_styles_xml(self):
        fd = zipfile.ZipFile(self.filename)
        data = fd.read('styles.xml')
        fd.close()
        return data

    def get_file(self, path):
        fd = zipfile.ZipFile(self.filename)
        data = fd.read(path)
        fd.close()
        return data

    def unpack(self, dstdir):
        fd = zipfile.ZipFile(self.filename)
        fd.extractall(path=dstdir)
        fd.close()


class _UnpackedODFHandler(object):

    def __init__(self, dirname):
        self.dirname = dirname

    def get_content_xml(self):
        fd = open(os.path.join(self.dirname, 'content.xml'), 'r')
        data = fd.read()
        fd.close()
        return data

    def get_meta_xml(self):
        fd = open(os.path.join(self.dirname, 'meta.xml'), 'r')
        data = fd.read()
        fd.close()
        return data

    def get_styles_xml(self):
        fd = open(os.path.join(self.dirname, 'styles.xml'), 'r')
        data = fd.read()
        fd.close()
        return data

    def get_file(self,path):
        fd = open(os.path.join(self.dirname, path), 'r')
        data = fd.read()
        fd.close()
        return data

    def unpack(self, dstdir):
        os.rmdir(dstdir)
        shutil.copytree(self.dirname, dstdir)


class Document():

    def close(self):
        self.file.close()
        if self.delete_on_close:
            self.delete()

    def delete(self):
        os.unlink(self.name)

    """Check if `f` is a file name and open the file in `mode`.
    A context manager."""
    def __init__(self, f, mode, buffering=1, delete_on_close=True):
        if isinstance(f, str):
            self.file = open(f, mode)
        else:
            self.file = f
        self.close_file = (self.file is not f)
        self.delete_on_close = delete_on_close
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args, **kwargs):
        if (not self.close_file):
            return  # do nothing
        # clean up
        exit = getattr(self.file, '__exit__', None)
        if exit is not None:
            return exit(*args, **kwargs)
        else:
            exit = getattr(self.file, 'close', None)
            if exit is not None:
                exit()
    
    def __getattr__(self, attr):
        return getattr(self.file, attr)
    
    def __iter__(self):
        return iter(self.file)


class HTMLDocument(Document):
    format = 'html'
    content_type = 'text/html'

    def get_content(self):
        fd = open(self.name, 'r')
        content = fd.read()
        fd.close()
        return content


class ODFDocument(Document):
    format = 'odt'
    content_type = 'application/vnd.oasis.opendocument.text'

    def get_content_xml(self):
        fd = zipfile.ZipFile(self.name)
        data = fd.read('content.xml')
        fd.close()
        return data

    def get_meta_xml(self):
        fd = zipfile.ZipFile(self.name)
        data = fd.read('meta.xml')
        fd.close()
        return data

    def get_styles_xml(self):
        fd = zipfile.ZipFile(self.name)
        data = fd.read('styles.xml')
        fd.close()
        return data
