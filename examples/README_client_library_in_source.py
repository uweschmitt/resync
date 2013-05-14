#!/usr/bin/env python
if (True): #keep indentation of README

    from resync.resource_list import ResourceList
    from resync.resource import Resource

    rl = ResourceList()
    rl.add( Resource('http://example.com/res1', lastmod='2013-01-01') )
    rl.add( Resource('http://example.com/res2', lastmod='2013-01-02') )
    print rl.as_xml()
