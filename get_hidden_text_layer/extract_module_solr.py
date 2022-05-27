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
            word = word.strip(",!?.:;/'\"\\-+=*^%$#@() ")
            if word == "":
                return

            word_dict = {
                'id': f"{where_to_find['file']}-{where_to_find['id']}",
                'file': where_to_find['file'],
                'page': where_to_find['page'],
                'line': where_to_find['line'],
                'position': where_to_find['pos'],
                'coordinates': coordinates_list,
                'word': word,
                'word-1': where_to_find['word1'],  # previous word
                'word-1-page-line-pos': where_to_find['word-1-page-line-pos']  # page and line of the previous word
            }
            where_to_find['id'] += 1
            where_to_find['word1'] = word
            where_to_find['word-1-page-line-pos'] = \
                f"{where_to_find['page']}_{where_to_find['line']}_{where_to_find['pos']}"

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

        where_to_find = {'word-1-page-line-pos': " ", 'word1': " ", 'file': djvu_path,
                         'page': 0, 'line': 0, 'pos': 0, 'id': 1}
        clean_index(solr_url, [djvu_path])
        for i, page in enumerate(document.pages):
            try:
                page.get_info(wait=True)
            except djvu.decode.JobFailed:
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


def print_result(begin_result, end_result):
    for i in range(len(begin_result)):
        s = begin_result[i]['word'][0]
        if begin_result[i]['id'] != end_result[i]['id']:
            s += " ... " + end_result[i]['word'][0]
        print(f"FOUND \" {s} \" near {begin_result[i]['file'][0]}: page {begin_result[i]['page'][0]},"
              f" line {begin_result[i]['line'][0]}, word number {begin_result[i]['position'][0]}")


def list_to_queries(words):
    """
    @param words: list of words
    @return: word - the last word of the list,
             query - a solr query made of the second and the third (from the end) words of the list
             (if the list is long enough)
             words_left
    """

    filter_query = []
    if len(words) > 1:
        filter_query.append(f"word-1:{words[-2]}~")

    return words[-1], filter_query, words[:-1]


def find_word(word_line, solr_url, accuracy=False, files=[""], limit=10000):
    """
    finds 'limit' entries of the word given
    @param accuracy: set it True if you need only exact matches
    @param word_line: words to find
    @param solr_url: url to connect to the Solr engine
    @param files: list of files to search into
    @param limit: maximum length of result, default 1e4
    @return: list of search results
    """

    words = [w.strip(",!?.:;/'\"\\-+=*^%$#@() ") for w in word_line.split()]
    word, filter_query, words_left = list_to_queries(words)
    if word is None:
        return []

    solr = pysolr.Solr(solr_url, timeout=10)

    begin_result, end_result = _find_word(word, filter_query, words_left, solr,
                                          accuracy=accuracy, files=files, limit=limit)

    if len(words) > 1:
        upd_begin_result = []
        for res in begin_result:
            page, line, pos = res['word-1-page-line-pos'][0].split('_')
            filter_query_ = [f"page:{page}", f"line:{line}", f"position:{pos}", f"file:{res['file'][0]}"]
            query_ = f"word:{res['word-1'][0]}~|*{res['word-1'][0]}*"
            new_res = solr.search(q=query_, fq=filter_query_)
            upd_begin_result.extend(list(new_res))

        begin_result = upd_begin_result

    return begin_result, end_result


def _recursive_search(solr, result, words, accuracy):
    """
    make a recursive search to find long collocations (> 3 words)
    @param solr: solr search engine object
    @param result: searching result for the tail of collocation
    @param words: words to search
    @param accuracy:
    @return: full searching result
    """
    full_result = []
    good_results_indexes = []
    for i, res in enumerate(result):
        page, line, position = res['word-1-page-line-pos'][0].split('_')
        add_query = [f"page:{page}", f"line:{line}", f"position:{position}"]
        word_, filter_query_, words_left = list_to_queries(words)
        res_, _ = _find_word(
                word_, filter_query_, words_left, solr,
                accuracy=accuracy, files=[res['file'][0]],
                additional_query=add_query
                )
        full_result.extend(res_)
        if len(res_) > 0:
            good_results_indexes.append(i)
    return full_result, good_results_indexes


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
            result.extend(list(solr.search(q=f"word:*{word}*", fq=filter_query, rows=limit)))
        if not accuracy:
            result.extend(list(solr.search(q=f"word:{word}~|*{word}*", fq=filter_query, rows=limit)))

        if len(file) > 0:
            filter_query.pop()
        else:
            break

    full_result = result.copy()
    upd_result = result.copy()
    if len(words_left) > 1:
        full_result, indexes = _recursive_search(solr, result, words_left, accuracy)
        upd_result = [result[i] for i in indexes]
    return full_result, upd_result


def check_index(solr_url, file):
    """
    checks if the file is already indexed
    @param solr_url: url to connect to the Solr engine
    @param file: file to check
    """
    solr = pysolr.Solr(solr_url, timeout=10)
    result = solr.search(q=f'id:"{file}-1"')
    return len(result) == 1



