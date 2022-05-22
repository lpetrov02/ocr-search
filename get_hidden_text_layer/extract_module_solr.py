import djvu.decode
import pysolr


def print_text(sexpr, text_file, level=0):
    """
    prints text from the DjVu text layer
    @param sexpr: sexpr which contains text
    @param text_file: file to write the text into
    @param level:
    """
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


def _index_word(words_buffer, word_tuple, where_to_find):
    """
    adds information about a word to the list (later it will be added to Solr index
    @param words_buffer: list of dicts with information about words' entries
    @param word_tuple: tuple with info about the word
    @param where_to_find: dict with current file, page, line, position of the word in the line and word id
    """
    if isinstance(word_tuple, tuple):
        if len(word_tuple) == 0:
            return
        if word_tuple[0] == djvu.sexpr.Symbol('word'):
            coordinates_list = [str(word_tuple[i]) for i in range(1, 5)]
            word = word_tuple[5]
            word_dict = {
                'id': f"{where_to_find['file']}-{where_to_find['id']}",
                'file': where_to_find['file'],
                'page': where_to_find['page'],
                'line': where_to_find['line'],
                'position': where_to_find['pos'],
                'coordinates': coordinates_list,
                'word': word
            }
            where_to_find['id'] += 1

            words_buffer.append(word_dict)


def _index_line(words_buffer, line_tuple, where_to_find):
    """
    cuts line into words
    @param words_buffer: list of dicts with information about words' entries
    @param line_tuple: tuple with information about the line
    @param where_to_find: dict with current file, page, line and word id
    """
    if isinstance(line_tuple, tuple):
        if len(line_tuple) == 0:
            return
        if line_tuple[0] == djvu.sexpr.Symbol('line'):
            for i, word_tuple in enumerate(line_tuple[5:]):
                where_to_find['pos'] = i
                _index_word(words_buffer, word_tuple, where_to_find)


def _index_page(words_buffer, sexpr, where_to_find):
    """
    cuts the page into lines
    @param words_buffer: list of dicts with information about words' entries
    @param sexpr: sexpr which contains information about the page
    @param where_to_find: dict with current file, page and word id
    """
    if isinstance(sexpr, djvu.sexpr.ListExpression):
        if len(sexpr) == 0:
            return
        if sexpr.value[0] == djvu.sexpr.Symbol('page'):
            for i, line_tuple in enumerate(sexpr.value[5:]):
                where_to_find['line'] = i
                _index_line(words_buffer, line_tuple, where_to_find)


def clean_index(solr_url, files=[]):
    """
    cleans index
    @param solr_url: url to connect to the Solr engine
    @param files: list of file to delete from index. If empty, everything will be deleted
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    if len(files) == 0:
        solr.delete(q='*:*')
    for file in files:
        solr.delete(q=f'file:"{file}"')
    solr.commit()


class Context(djvu.decode.Context):

    def process(self, djvu_path, text_file, pages=[]):
        """
        prints text from DjVu into a text file
        @param djvu_path: path to the DjVu file
        @param text_file: path to the text file
        @param pages: pages to index. If not given, full text will be extracted
        """
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

    def index_text(self, djvu_path, solr_url, pages=[]):
        """
        indexes text from the file
        @param djvu_path: path to the file to index
        @param solr_url: url to connect to the Solr engine
        @param pages: pages to index. If not given, full text will be indexed
        """
        try:
            document = self.new_document(djvu.decode.FileURI(djvu_path))
        except djvu.decode.JobFailed:
            raise Exception("JobFailed: unable to create a 'document'")

        solr = pysolr.Solr(solr_url, timeout=10)

        where_to_find = {'file': djvu_path, 'page': 0, 'line': 0, 'pos': 0, 'id': 1}
        clean_index(solr_url, [djvu_path])
        for i, page in enumerate(document.pages):
            try:
                page.get_info(wait=True)
            except djvu.decode.JobFailed:
                # raise Exception("JobFailed: unable to get page information")
                continue

            if i not in pages and pages != []:
                continue

            words_buffer = []
            where_to_find['page'] = i
            _index_page(words_buffer, page.text.sexpr, where_to_find)
            solr.add(words_buffer)
        solr.commit()


def dump_text(djvu_path, text_file_path, pages=[]):
    text_file = open(text_file_path, 'w')
    context = Context()
    context.process(djvu_path, text_file, pages)


def dump_and_index_text(djvu_path, solr_url, pages=[]):
    context = Context()
    try:
        context.index_text(djvu_path, solr_url, pages)
    except Exception as e:
        raise Exception(e.args)


def find_word(word, solr_url, files=[], limit=1000000000):
    """
    finds 'limit' entries of the word given
    @param word: word to find
    @param solr_url: url to connect to the Solr engine
    @param files: list of files to search into
    @param limit: maximum length of result, default 1e9
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    for file in files:
        result = solr.search(q=f'word:"{word}"', fq=f'file:"{file}"', rows=limit)
        for record in result:
            print(record)


def check_index(solr_url, file):
    """
    checks if the file is already indexed
    @param solr_url: url to connect to the Solr engine
    @param file: file to check
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    result = solr.search(q=f'id:"{file}-1"')
    return len(result) == 1
