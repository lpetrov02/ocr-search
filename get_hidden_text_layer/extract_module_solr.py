import djvu.decode
import pysolr
from tqdm import tqdm
import solr_stats


def get_index_info():
    stats = solr_stats.SolrStats()
    res = stats.get_indexed_files()
    stats.close()
    return res


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


def _index_word(words_buffer, word_tuple, word_info):
    """
    adds information about a word to the list (later it will be added to Solr index
    @param words_buffer: list of dicts with information about words' entries
    @param word_tuple: tuple with info about the word
    @param word_info: dict with current file, page, line, position of the word in the line and word id
    """
    try:
        if isinstance(word_tuple, tuple):
            if len(word_tuple) == 0:
                return
            if word_tuple[0] == djvu.sexpr.Symbol('word'):
                coordinates_list = "_".join([str(word_tuple[i]) for i in range(1, 5)])
                word = word_tuple[5]
                word = word.strip(",!?.:;/'\"\\-+=*^%$#@() ")
                if word == "":
                    return

                page_line_pos = '_'.join([str(word_info[key]) for key in ['page', 'line', 'pos']])
                word_dict = {
                    'id': f"{word_info['file']}-{word_info['id']}",
                    'file': word_info['file'],
                    'page-line-pos': page_line_pos,
                    'coords': coordinates_list,
                    'word': word,
                    'word-1': word_info['word1'],  # previous word
                    'word-1-page-line-pos': word_info['word-1-page-line-pos']  # page and line of the previous word
                }
                word_info['id'] += 1
                word_info['word1'] = word
                word_info['word-1-page-line-pos'] = page_line_pos

                words_buffer.append(word_dict)
    except UnicodeDecodeError:
        return


def add_single_word(solr_url, word, file_name, coordinates=[], plp=" ", word_1="", plp_1=" "):
    """
    adds a single word to the index
    @param solr_url:
    @param word:
    @param file_name:
    @param coordinates:
    @param plp: str '<page>_<line>_<position>' of the word
    @param word_1: previous word
    @param plp_1: str '<page>_<line>_<position>' of the previous word
    @return:
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    stats = solr_stats.SolrStats()

    new_word_id = stats.get_number_of_recordings(file_name)
    word_dict = {
        'id': f"{file_name}-{new_word_id}",
        'file': file_name,
        'page-line-pos': plp,
        'coords': coordinates,
        'word': word,
        'word-1': word_1,  # previous word
        'word-1-page-line-pos': plp_1  # page and line of the previous word
    }

    solr.add(word_dict)
    solr.commit()
    stats.add_words(1)
    stats.close()


def _index_line(words_buffer, line_tuple, word_info):
    """
    cuts line into words
    @param words_buffer: list of dicts with information about words' entries
    @param line_tuple: tuple with information about the line
    @param word_info: dict with current file, page, line and word id
    """
    try:
        if isinstance(line_tuple, tuple):
            if len(line_tuple) == 0:
                return
            if line_tuple[0] == djvu.sexpr.Symbol('line'):
                for i, word_tuple in enumerate(line_tuple[5:]):
                    word_info['pos'] = i
                    _index_word(words_buffer, word_tuple, word_info)
    except UnicodeDecodeError:
        return


def _index_page(words_buffer, pages_skipped, sexpr, word_info):
    """
    cuts the page into lines
    @param words_buffer: list of dicts with information about words' entries
    @param sexpr: sexpr which contains information about the page
    @param word_info: dict with current file, page and word id
    """
    try:
        if isinstance(sexpr, djvu.sexpr.ListExpression):
            if len(sexpr) == 0:
                return
            if sexpr.value[0] == djvu.sexpr.Symbol('page'):
                for i, line_tuple in enumerate(sexpr.value[5:]):
                    word_info['line'] = i
                    _index_line(words_buffer, line_tuple, word_info)
    except UnicodeDecodeError:
        pages_skipped.append(word_info['page'])
        return


def clean_index(solr_url, files=[""]):
    """
    cleans index
    @param solr_url: url to connect to the Solr engine
    @param files: list of file to delete from index. "" - means cleaning the whole index.
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    stats = solr_stats.SolrStats()

    for file in files:
        if len(file) == 0:
            solr.delete(q='*:*')
        else:
            solr.delete(q=f'file:"{file}"')

    stats.delete_from_index(files)
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

    def index_text(self, djvu_path, solr_url, pages=[], progress_bar=False):
        """
        indexes text from the file
        @param reindex: set it True to reindex file which is indexed already
        @param progress_bar: set True to see a progress bar
        @param djvu_path: path to the file to index
        @param solr_url: url to connect to the Solr engine
        @param pages: pages to index. If not given, full text will be indexed
        """
        try:
            document = self.new_document(djvu.decode.FileURI(djvu_path))
        except djvu.decode.JobFailed:
            return -1, "Cannot open the djvu file"

        solr = pysolr.Solr(solr_url, timeout=10)
        stats = solr_stats.SolrStats()

        word_info = {'word-1-page-line-pos': " ", 'word1': " ", 'file': djvu_path,
                     'page': 0, 'line': 0, 'pos': 0, 'id': 0}
        clean_index(solr_url, [djvu_path])

        words_buffer = []
        pages_skipped = []
        total_recordings = 0
        for i, page in tqdm(enumerate(document.pages), desc='indexing', unit=' pages',
                            disable=not progress_bar, total=len(document.pages)):
            try:
                page.get_info(wait=True)
            except djvu.decode.JobFailed:
                continue

            if i not in pages and pages != []:
                continue

            words_buffer.clear()
            word_info['page'] = i
            _index_page(words_buffer, pages_skipped, page.text.sexpr, word_info)
            solr.add(words_buffer)
            total_recordings += len(words_buffer)

        solr.commit()
        stats.add_words(djvu_path, total_recordings)
        stats.add_skipped_pages(djvu_path, len(pages_skipped))
        stats.close()

        return total_recordings, "Indexing finished successfully"


def dump_text(djvu_path, text_file_path, pages=[]):
    text_file = open(text_file_path, 'w')
    context = Context()
    context.process(djvu_path, text_file, pages)


def dump_and_index_text(djvu_path, solr_url, pages=[], print_info=False, progress_bar=False, reindex=False):
    context = Context()
    if not check_index(solr_url, djvu_path) or reindex:
        recordings_added, message = context.index_text(djvu_path, solr_url, pages, progress_bar=progress_bar)
        if print_info:
            print(message)
            if recordings_added != -1:
                print(recordings_added, "recordings added")
    elif print_info:
        print("File already indexed. Rerun with reindex=True if you want to reindex it.")


def check_index(solr_url, file):
    """
    checks if the file is already indexed
    @param solr_url: url to connect to the Solr engine
    @param file: file to check
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    result = solr.search(q=f'id:"{file}-1"')
    return len(result) == 1