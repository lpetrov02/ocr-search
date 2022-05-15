#! /usr/bin/env python

from tqdm.notebook import tqdm
import sys
import djvu.decode
from optparse import OptionParser
import MySQLdb, MySQLdb.cursors
from MySQLdb import _mysql
import mysql.connector

import extract_module_v2 as extract


parser = OptionParser()
parser.add_option('-f', '--file', default="",    help='file to decode', action='store', dest='djvu_path')
parser.add_option('-a', '--action', default="",    help='what_to_do', action='store', dest='action')
parser.add_option('-o', '--output', default=False,    help='if you need output', action='store_true', dest='out')
parser.add_option('-w', '--word', default="",    help='word to find', action='store', dest='word')
parser.add_option('-e', '--exactly', default=False,
                  help='if you want to find exactly the word you mentioned in "-w"',
                  action='store_true', dest='exactly')

(options, args) = parser.parse_args()

try:
    if options.action == 'index':
        db_cursor = extract.dump_and_index_text(options.djvu_path)
    if options.action == 'print':
        extract.dump_text(options.djvu_path, "textfile.txt")
    if options.action == 'clean':
        extract.clean_index()
    if options.action == 'find':
        extract.find_word(options.word, options.exactly)


except Exception as e:
    print(e.args)
    sys.exit(-1)
