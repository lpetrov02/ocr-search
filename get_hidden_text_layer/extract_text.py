#! /usr/bin/env python

from optparse import OptionParser

import extract_module_solr as indexer
import solr_search as searcher


# your solr_url:
solr_url = "http://localhost:8983/solr/Solr_sample"


parser = OptionParser()
parser.add_option('-f', '--file', default="",    help='file to decode', action='store', dest='djvu_path')
parser.add_option('-a', '--action', default="",    help='what_to_do', action='store', dest='action')
parser.add_option('-r', '--reindex', default=False,    help='reindex file', action='store_true', dest='reindex')
parser.add_option('-A', '--accurate', default=False,    help='accurate search', action='store_true', dest='accuracy')
parser.add_option('-p', '--progress-bar', default=False,    help='progress bar', action='store_true', dest='pb')
parser.add_option('-w', '--word', default="",    help='word to find', action='store', dest='word')

(options, args) = parser.parse_args()

if options.action == 'index':
    indexer.dump_and_index_text(options.djvu_path, solr_url, print_info=True,
                                progress_bar=options.pb, reindex=options.reindex)

if options.action == 'print':
    indexer.dump_text(options.djvu_path, "textfile.txt")

if options.action == 'clean':
    indexer.clean_index(solr_url, [options.djvu_path])

if options.action == 'find':
    searching_result = searcher.find_word(options.word, solr_url, files=[options.djvu_path], accuracy=options.accuracy)
    searcher.print_result(searching_result)

if options.action == 'info':
    index_info = indexer.get_index_info()
    for file_info in index_info:
        print(file_info[1], ":", file_info[2], "words indexed")


