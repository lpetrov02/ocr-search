#! /usr/bin/env python

from tqdm.notebook import tqdm
import sys
import djvu.decode
from optparse import OptionParser

import extract_module_solr as extract


solr_url = "http://localhost:8983/solr/Solr_sample"


parser = OptionParser()
parser.add_option('-f', '--file', default="",    help='file to decode', action='store', dest='djvu_path')
parser.add_option('-a', '--action', default="",    help='what_to_do', action='store', dest='action')
parser.add_option('-r', '--reindex', default=False,    help='reindex file', action='store_true', dest='reindex')
parser.add_option('-w', '--word', default="",    help='word to find', action='store', dest='word')

(options, args) = parser.parse_args()

try:
    if options.action == 'index':
        if not extract.check_index(solr_url, options.djvu_path) or options.reindex:
            extract.dump_and_index_text(options.djvu_path, solr_url)

    if options.action == 'print':
        extract.dump_text(options.djvu_path, "textfile.txt")

    if options.action == 'clean':
        if len(options.djvu_path) == 0:
            extract.clean_index(solr_url)
        else:
            extract.clean_index(solr_url, [options.djvu_path])

    if options.action == 'find':
        extract.find_word(options.word, solr_url, files=[options.djvu_path])

except Exception as e:
    print(e.args)
    sys.exit(-1)

