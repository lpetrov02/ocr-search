import djvu.decode
import pysolr
from tqdm import tqdm


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


def _index_line(words_buffer, line_tuple, word_info):
    """
    cuts line into words
    @param words_buffer: list of dicts with information about words' entries
    @param line_tuple: tuple with information about the line
    @param word_info: dict with current file, page, line and word id
    """
    if isinstance(line_tuple, tuple):
        if len(line_tuple) == 0:
            return
        if line_tuple[0] == djvu.sexpr.Symbol('line'):
            for i, word_tuple in enumerate(line_tuple[5:]):
                word_info['pos'] = i
                _index_word(words_buffer, word_tuple, word_info)


def _index_page(words_buffer, sexpr, word_info):
    """
    cuts the page into lines
    @param words_buffer: list of dicts with information about words' entries
    @param sexpr: sexpr which contains information about the page
    @param word_info: dict with current file, page and word id
    """
    if isinstance(sexpr, djvu.sexpr.ListExpression):
        if len(sexpr) == 0:
            return
        if sexpr.value[0] == djvu.sexpr.Symbol('page'):
            for i, line_tuple in enumerate(sexpr.value[5:]):
                word_info['line'] = i
                _index_line(words_buffer, line_tuple, word_info)


def clean_index(solr_url, files=[]):
    """
    cleans index
    @param solr_url: url to connect to the Solr engine
    @param files: list of file to delete from index. "" - means cleaning the whole index.
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    for file in files:
        if len(file) == 0:
            solr.delete(q='*:*')
        else:
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
            return -1

        solr = pysolr.Solr(solr_url, timeout=10)

        word_info = {'word-1-page-line-pos': " ", 'word1': " ", 'file': djvu_path,
                     'page': 0, 'line': 0, 'pos': 0, 'id': 1}
        clean_index(solr_url, [djvu_path])

        words_buffer = []
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
            _index_page(words_buffer, page.text.sexpr, word_info)
            solr.add(words_buffer)
            total_recordings += len(words_buffer)
        solr.commit()

        return total_recordings


def dump_text(djvu_path, text_file_path, pages=[]):
    text_file = open(text_file_path, 'w')
    context = Context()
    context.process(djvu_path, text_file, pages)


def dump_and_index_text(djvu_path, solr_url, pages=[], print_info=False, progress_bar=False, reindex=False):
    context = Context()
    if not check_index(solr_url, djvu_path) or reindex:
        recordings_added = context.index_text(djvu_path, solr_url, pages, progress_bar=progress_bar)
        if print_info:
            print("Indexing finished.", recordings_added, "recordings added")
    elif print_info:
        print("File already indexed. Rerun with reindex=True if you want to reindex it.")


def print_result(searching_result):
    for res in searching_result:
        s = res[0]['word'][0]
        if res[0]['id'] != res[1]['id']:
            s += " ... " + res[1]['word'][0]
        page, line, pos = res[0]['page-line-pos'][0].split('_')
        print(f"FOUND \" {s} \" near {res[0]['file'][0]}: page {page},"
              f" line {line}, word number {pos}")


def list_to_queries(words, accuracy=False):
    """
    takes a list of words and returns the last word of this list, the filter query to search for this word and bites
    the last word off the list
    @param accuracy: set it True if you need only exact matches
    @param words: list of words
    @return: word - the last word of the list,
             query - a solr query made of the second and the third (from the end) words of the list
             (if the list is long enough)
    """

    filter_query = []
    if len(words) > 1:
        if accuracy:
            filter_query.append(f"word-1:{words[-2]}")
        else:
            filter_query.append(f"word-1:{words[-2]}~|*{words[-2]}*")
    word = words.pop()

    return word, filter_query


def find_word(word_line, solr_url, accuracy=False, files=[""], limit=10000):
    """
    finds entries of the word or collocation given
    @param accuracy: set it True if you need only exact matches
    @param word_line: words to find
    @param solr_url: url to connect to the Solr engine
    @param files: list of files to search into
    @param limit: maximum length of result, default 1e4
    @return: list of search results
    """

    words = [w.strip(",!?.:;/'\"\\-+=*^%$#@() ") for w in word_line.split()]
    word, filter_query = list_to_queries(words, accuracy)  # words -> words[:-1]
    if word is None:
        return []

    solr = pysolr.Solr(solr_url, timeout=10)

    begin_result, end_result = _find_word(word, filter_query, words, solr,
                                          accuracy=accuracy, files=files, limit=limit)

    # if we search not for a single word but for a collocation, we would prefer (I believe)
    # to get information about the first word of the entry, not about the second!
    if len(words) > 0:
        upd_begin_result = []
        for res in begin_result:
            filter_query_ = [f"page-line-pos:{res['word-1-page-line-pos'][0]}", f"file:{res['file'][0]}"]
            query_ = f"word:{res['word-1'][0]}~|*{res['word-1'][0]}*"
            new_res = solr.search(q=query_, fq=filter_query_)
            upd_begin_result.extend(list(new_res))

        begin_result = upd_begin_result

    return list(zip(begin_result, end_result))


def _recursive_search(solr, result, words, accuracy):
    """
    make a recursive search to find long collocations (> 2 words)
    @param solr: solr search engine object
    @param result: searching result for the tail of collocation
    @param words: words to search
    @param accuracy:
    @return: full searching result
    """
    full_result = []
    good_results = []
    word_, filter_query_ = list_to_queries(words, accuracy)  # words -> words[:-1]
    for i, res in enumerate(result):
        add_query = [f"page-line-pos:{res['word-1-page-line-pos'][0]}"]
        res_, _ = _find_word(
                word_, filter_query_, words, solr,
                accuracy=accuracy, files=[res['file'][0]],
                additional_query=add_query
                )  # inside this func filter_query_ is extended with 1-element add_query
        filter_query_.pop()
        if len(res_) > 0:
            full_result.extend(res_)
            good_results.append(res)
    words.append(word_)
    return full_result, good_results


def _find_word(word, filter_query, words_left, solr, accuracy=False, files=[""], limit=10000, additional_query=[]):
    """
    finds 'limit' entries of the word given
    @param accuracy: set it True if you need only exact matches
    @param word: word to find
    @param solr: Solr engine
    @param files: list of files to search into
    @param limit: maximum length of result, default 1e4
    @return: list of search results
    """
    filter_query.extend(additional_query)

    result = []
    for file in files:
        if len(file) > 0:
            filter_query.append(f"file:{file}")

        if accuracy:
            result.extend(list(solr.search(q=f"word:{word}*", fq=filter_query, rows=limit)))
        if not accuracy:
            result.extend(list(solr.search(q=f"word:{word}~|*{word}*", fq=filter_query, rows=limit)))

        if len(file) > 0:
            filter_query.pop()
        else:
            break

    end_result = result.copy()
    begin_result = result.copy()
    if len(words_left) > 1:
        begin_result, end_result = _recursive_search(solr, result, words_left, accuracy)

    return begin_result, end_result


def check_index(solr_url, file):
    """
    checks if the file is already indexed
    @param solr_url: url to connect to the Solr engine
    @param file: file to check
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    result = solr.search(q=f'id:"{file}-1"')
    return len(result) == 1

