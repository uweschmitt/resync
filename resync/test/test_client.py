import unittest
import re
import logging
import shutil
import sys, StringIO, contextlib
import tempfile

from resync.client import Client, ClientFatalError
from resync.mapper import MapperError

# From http://stackoverflow.com/questions/2654834/capturing-stdout-within-the-same-process-in-python
class Data(object):
    pass

@contextlib.contextmanager
def capture_stdout():
    old = sys.stdout
    capturer = StringIO.StringIO()
    sys.stdout = capturer
    data = Data()
    yield data
    sys.stdout = old
    data.result = capturer.getvalue()

# From http://stackoverflow.com/questions/13379742/right-way-to-clean-up-a-temporary-folder-in-python-class
@contextlib.contextmanager
def temporary_directory(*args, **kwargs):
    d = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield d
    finally:
        shutil.rmtree(d)

class TestClient(unittest.TestCase):

    def setUp(self):
        # setup logstream so we can readily check for new output in any test
        self._logstream = StringIO.StringIO()
        self._handler = logging.StreamHandler(self._logstream)
        self._log = logging.getLogger()
        self._log.setLevel(logging.DEBUG)
        for handler in self._log.handlers: 
            self._log.removeHandler(handler)
        self._log.addHandler(self._handler)

    def clearLog(self):
        self._logstream.truncate(0)

    def assertLogMatches(self, r):
        if sys.version_info < (2, 7):
            return self.assertTrue( re.search(r,self._logstream.getvalue()) )
        else: #assume for 2.7, nicer debugging...
            return self.assertRegexpMatches( self._logstream.getvalue(), r )

    def tearDown(self):
        self._log.removeHandler(self._handler)
        self._handler.close()

    def test01_make_resource_list_empty(self):
        c = Client()
        # No mapping is an error
        self.assertRaises( ClientFatalError, c.build_resource_list )

    def test02_source_uri(self):
        c = Client()
        # uris
        self.assertEqual( c.sitemap_uri('http://example.org/path'), 'http://example.org/path')
        self.assertEqual( c.sitemap_uri('info:whatever'), 'info:whatever')
        self.assertEqual( c.sitemap_uri('http://example.org'), 'http://example.org')
        # absolute local
        self.assertEqual( c.sitemap_uri('/'), '/')
        self.assertEqual( c.sitemap_uri('/path/anything'), '/path/anything')
        self.assertEqual( c.sitemap_uri('/path'), '/path')
        # relative, must have mapper
        self.assertRaises( MapperError, c.sitemap_uri, 'a' )
        c.set_mappings( ['http://ex.a/','/a'])
        self.assertEqual( c.sitemap_uri('a'), 'http://ex.a/a')

    def test03_build_resource_list(self):
        c = Client()
        c.set_mappings( ['http://ex.a/','testdata/dir1'])
        rl = c.build_resource_list(paths='testdata/dir1')
        self.assertEqual( len(rl), 2 )
        # check max_sitemap_entries set in resulting resourcelist
        c.max_sitemap_entries=9
        rl = c.build_resource_list(paths='testdata/dir1')
        self.assertEqual( len(rl), 2 )
        self.assertEqual( rl.max_sitemap_entries, 9 )

    def test04_log_event(self):
        c = Client()
        c.log_event("xyz")
        self.assertLogMatches( "Event: 'xyz'" )

    def test05_baseline_or_audit_steps1to4(self):
        # Not setup...
        c = Client()
        self.assertRaises( ClientFatalError, c.baseline_or_audit )
        c.set_mappings( ['http://example.org/bbb','/tmp/this_does_not_exist'] )
        self.assertRaises( ClientFatalError, c.baseline_or_audit )
        c.set_mappings( ['/tmp','/tmp']) #unsafe
        self.assertRaises( ClientFatalError, c.baseline_or_audit )
        # empty list to get no resources error
        c = Client()
        c.set_mappings( ['testdata/empty_lists','testdata/empty_lists'])
        self.assertRaises( ClientFatalError, c.baseline_or_audit, audit_only=True )
        # checksum will be set False if source list has no md5 sums
        c = Client()
        c.set_mappings( ['testdata/dir1_src_in_sync','testdata/dir1'])
        c.checksum=True
        c.baseline_or_audit(audit_only=True)
        self.assertFalse( c.checksum )
        # include resource in other domain (exception unless noauth set)
        c = Client()
        c.set_mappings( ['testdata/dir1_src_with_ext','testdata/dir1'])
        self.assertRaises( ClientFatalError, c.baseline_or_audit, audit_only=False )

    def test06_baseline_or_audit_step5(self):
        # use test data for src, make dir for destination
        src = 'testdata/client_src1'
        with temporary_directory() as tmp_dst:
            c = Client()
            c.set_mappings( [src, tmp_dst] )
            c.baseline_or_audit()
            self.assertLogMatches( r'Status:\s+NOT IN SYNC \(same=0, to create=3, to update=0, to delete=0\)' )
            self.clearLog()
            src = 'testdata/client_src2'
            c.set_mappings( [src, tmp_dst] )
            c.baseline_or_audit(allow_deletion=True)
            self.assertLogMatches( r'Status:\s+SYNCED \(same=1, created=1, updated=1, deleted=1\)' )
            # follow on with incremental
            self.clearLog()
            src = 'testdata/client_src3'
            c.set_mappings( [src, tmp_dst] )
            c.incremental(from_datetime="2015-01-01T01:01:01Z")
            self.assertLogMatches( r'Read source change list, 1 changes listed' )
            self.assertLogMatches( r'Status: CHANGES APPLIED \(created=1, updated=0, deleted=0\)' )

    def test07_write_capability_list(self):
        c = Client()
        with capture_stdout() as capturer:
            c.write_capability_list( { 'a':'uri_a', 'b':'uri_b' } )
        self.assertTrue( re.search(r'<urlset ',capturer.result) )
        self.assertTrue( re.search(r'<rs:md capability="capabilitylist" />',capturer.result) )
        self.assertTrue( re.search(r'<url><loc>uri_a</loc><rs:md capability="a"',capturer.result) )
        self.assertTrue( re.search(r'<url><loc>uri_b</loc><rs:md capability="b"',capturer.result) )

    def test08_write_source_description(self):
        c = Client()
        with capture_stdout() as capturer:
            c.write_source_description( [ 'a','b','c' ] )
        #print capturer.result
        self.assertTrue( re.search(r'<urlset ',capturer.result) )
        self.assertTrue( re.search(r'<rs:md capability="description" />',capturer.result) )
        self.assertTrue( re.search(r'<url><loc>a</loc><rs:md capability="capabilitylist" /></url>',capturer.result) )
        self.assertTrue( re.search(r'<url><loc>b</loc><rs:md capability="capabilitylist" /></url>',capturer.result) )

    def test20_parse_document(self):
        # Key property of the parse_document() method is that it parses the
        # document and identifies its type
        c = Client()
        with capture_stdout() as capturer:
            c.sitemap_name='testdata/examples_from_spec/resourcesync_ex_1.xml'
            c.parse_document()
        self.assertTrue( re.search(r'Parsed resourcelist document with 2 entries',capturer.result) )
        with capture_stdout() as capturer:
            c.sitemap_name='testdata/examples_from_spec/resourcesync_ex_17.xml'
            c.parse_document()
        self.assertTrue( re.search(r'Parsed resourcedump document with 3 entries',capturer.result) )
        with capture_stdout() as capturer:
            c.sitemap_name='testdata/examples_from_spec/resourcesync_ex_19.xml'
            c.parse_document()
        self.assertTrue( re.search(r'Parsed changelist document with 4 entries',capturer.result) )
        with capture_stdout() as capturer:
            c.sitemap_name='testdata/examples_from_spec/resourcesync_ex_22.xml'
            c.parse_document()
        self.assertTrue( re.search(r'Parsed changedump document with 3 entries',capturer.result) )

    def test40_write_resource_list_mappings(self):
        c = Client()
        c.set_mappings( ['http://example.org/','testdata/'] )
        # with no explicit paths seting the mapping will be used
        with capture_stdout() as capturer:
            c.write_resource_list()
        #sys.stderr.write(capturer.result)
        self.assertTrue( re.search(r'<rs:md at="\S+" capability="resourcelist"', capturer.result ) )
        self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_a</loc>', capturer.result ) )
        self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_b</loc>', capturer.result ) )
        self.assertTrue( re.search(r'<url><loc>http://example.org/dir2/file_x</loc>', capturer.result ) )

    def test41_write_resource_list_path(self):
        c = Client()
        c.set_mappings( ['http://example.org/','testdata/'] )
        # with an explicit paths setting only the specified paths will be included
        with capture_stdout() as capturer:
            c.write_resource_list(paths='testdata/dir1')
        sys.stderr.write(capturer.result)
        self.assertTrue( re.search(r'<rs:md at="\S+" capability="resourcelist"', capturer.result ) )
        self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_a</loc>', capturer.result ) )
        self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_b</loc>', capturer.result ) )
        self.assertFalse( re.search(r'<url><loc>http://example.org/dir2/file_x</loc>', capturer.result ) )
        # Travis CI does not preserve timestamps from github so test here for the file
        # size but not the datestamp
        #self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_a</loc><lastmod>[\w\-:]+</lastmod><rs:md length="20" /></url>', capturer.result ) )
        #self.assertTrue( re.search(r'<url><loc>http://example.org/dir1/file_b</loc><lastmod>[\w\-:]+</lastmod><rs:md length="45" /></url>', capturer.result ) )

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestClient)
    unittest.TextTestRunner(verbosity=2).run(suite)
