from tqdm.notebook import tqdm
import sys
import djvu.decode
import pysolr


record_id = 1
solr_url = "http://localhost:8983/solr/Solr_sample"
# TODO: remove it from here, make it an argument of the command line


def print_text(sexpr, text_file, level=0):
    if level > 0:
        text_file.write(' ' * (2 * level - 1) + ' ')
    if isinstance(sexpr, djvu.sexpr.ListExpression):
        if len(sexpr) == 0:
            return
        text_file.write(str(sexpr[0].value))
        text_file.write(str([sexpr[i].value for i in range(1, 5)]) + "\n")
        for child in sexpr[5:]:
            print_text(child, text_file, level + 1)
    else:
        text_file.write('"' + sexpr.value + '"' + "\n")


def index_word(words_buffer, word_tuple, page_number, line_number, word_number):
    if isinstance(word_tuple, tuple):
        if len(word_tuple) == 0:
            return
        if word_tuple[0] == djvu.sexpr.Symbol('word'):
            coordinates_list = [str(word_tuple[i]) for i in range(1, 5)]
            word = word_tuple[5]
            global record_id
            # TODO: don't use global variables!!
            # TODO: can I have integers here?
            word_dict = {
                'id': record_id,
                'page': str(page_number),
                'line': str(line_number),
                'position': str(word_number),
                'coordinates': ','.join(coordinates_list),
                'word': word
            }
            record_id += 1

            words_buffer.append(word_dict)


def index_line(words_buffer, line_tuple, page_number, line_number):
    if isinstance(line_tuple, tuple):
        if len(line_tuple) == 0:
            return
        if line_tuple[0] == djvu.sexpr.Symbol('line'):
            for i, word_tuple in enumerate(line_tuple[5:]):
                index_word(words_buffer, word_tuple, page_number, line_number, i)


def index_page(words_buffer, sexpr, page_number):
    if isinstance(sexpr, djvu.sexpr.ListExpression):
        if len(sexpr) == 0:
            return
        if sexpr.value[0] == djvu.sexpr.Symbol('page'):
            for i, line_tuple in enumerate(sexpr.value[5:]):
                index_line(words_buffer, line_tuple, page_number, i)


class Context(djvu.decode.Context):

    def process(self, djvu_path, text_file, pages=[]):
        try:
            document = self.new_document(djvu.decode.FileURI(djvu_path))
        except djvu.decode.JobFailed:
            raise Exception("JobFailed: unable to create a 'document'")

        for i, page in enumerate(document.pages):

            try:
                page.get_info(wait=True)
            except djvu.decode.JobFailed:
                raise Exception("JobFailed: unable to get page information")

            if i not in pages and pages != []:
                continue
            print(i)
            print_text(page.text.sexpr, text_file)

    def index_text(self, djvu_path, pages=[]):
        try:
            document = self.new_document(djvu.decode.FileURI(djvu_path))
            solr = pysolr.Solr(solr_url, timeout=10)
        except djvu.decode.JobFailed:
            raise Exception("JobFailed: unable to create a 'document'")

        for i, page in enumerate(document.pages):
            try:
                page.get_info(wait=True)
            except djvu.decode.JobFailed:
                raise Exception("JobFailed: unable to get page information")

            if i not in pages and pages != []:
                continue

            words_buffer = []
            index_page(words_buffer, page.text.sexpr, i)
            docs = [
                {'id': 1, 'name': 'document 1', 'text': u'Paul Verlaine'},
                {'id': 2, 'name': 'document 2', 'text': u'Владимир Маякoвский'},
                {'id': 3, 'name': 'document 3', 'text': u'test'},
                {'id': 4, 'name': 'document 4', 'text': u'test'}
            ]
            solr.add(words_buffer)
            solr.add(docs)


def dump_text(djvu_path, text_file_path, pages=[]):
    text_file = open(text_file_path, 'w')
    context = Context()
    context.process(djvu_path, text_file, pages)


def dump_and_index_text(djvu_path, pages=[]):
    context = Context()
    try:
        context.index_text(djvu_path, pages)
    except Exception as e:
        raise Exception(e.args[0])


def clean_index():
    solr = pysolr.Solr(solr_url, timeout=10)
    solr.delete(q='*:*')


def find_word(word):
    solr = pysolr.Solr(solr_url, timeout=10)
    result = solr.search(q=f'word:"{word}"')

    for record in result:
        print(record)

