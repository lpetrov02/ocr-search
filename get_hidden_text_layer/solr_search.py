import pysolr


def print_result(searching_result):
    """
    prints the searching result beautifully
    @param searching_result: the searching result itself
    """
    for res in searching_result:
        s = res[0]['word'][0]
        if res[0]['id'] != res[1]['id']:
            s += " ... " + res[1]['word'][0]
        page, line, pos = res[0]['page-line-pos'][0].split('_')
        print(f"FOUND \" {s} \" near {res[0]['file'][0]}: page {page},"
              f" line {line}, word number {pos}")


def _get_queries(words, accuracy=False):
    """
    takes a list of words and makes queries for the solr engine.
    also pops the last element from 'words'
    @param accuracy: set it True to have only exact matches
    @param words: list of words
    @return: word - the last word of the list,
             query - a solr query to search the last and the pre-last words together,
             if there's more than 1 word in 'words'
    """

    filter_query = []
    if len(words) > 1:
        if accuracy:
            filter_query.append(f"word-1:{words[-2]}")
        else:
            filter_query.append(f"word-1:{words[-2]}~|*{words[-2]}*")
    word = words.pop()

    return word, filter_query


def _update_begin_result(solr, begin_result):
    """
    we have list of dicts with information about the second word of the collocation
    (if there are not less than two words) for each entry.
    but we need information about the first one.
    @param solr: solr engine to search
    @param begin_result:
    @return:
    """
    upd_begin_result = []
    for res in begin_result:
        filter_query_ = [f"page-line-pos:{res['word-1-page-line-pos'][0]}", f"file:{res['file'][0]}"]
        query_ = f"word:{res['word-1'][0]}~|*{res['word-1'][0]}*"
        new_res = solr.search(q=query_, fq=filter_query_)
        upd_begin_result.extend(list(new_res))
    return upd_begin_result


def find_word(words_collocation, solr_url, accuracy=False, files=[""], limit=10000):
    """
    finds entries of the word or collocation given
    @param accuracy: set it True if you need only exact matches
    @param words_collocation: the collocation to find
    @param solr_url: url to connect to the Solr engine
    @param files: list of files to search into
    @param limit: maximum length of result, default 1e4
    @return: list of search results
    """

    words = [w.strip(",!?.:;/'\"\\-+=*^%$#@() ") for w in words_collocation.split()]
    word, filter_query = _get_queries(words, accuracy)  # words -> words[:-1]
    if word is None:
        return []

    solr = pysolr.Solr(solr_url, timeout=10)

    begin_result, end_result = _find_word(word, filter_query, words, solr,
                                          accuracy=accuracy, files=files, limit=limit)

    if len(words) > 0:
        begin_result = _update_begin_result(solr, begin_result)

    return list(zip(begin_result, end_result))


def _recursive_search(solr, result, words, accuracy):
    """
    make a recursive search to find long collocations (> 2 words)
    @param solr: solr search engine object
    @param result: searching result for the tail of collocation
    @param words: words to search
    @param accuracy: set it True to have only exact matches
    @return: full searching result
    """
    full_result = []
    good_results = []
    word_, filter_query_ = _get_queries(words, accuracy)  # words -> words[:-1], word_
    for i, res in enumerate(result):
        add_query = [f"page-line-pos:{res['word-1-page-line-pos'][0]}"]
        res_, _ = _find_word(
                word_, filter_query_.copy(), words, solr,
                accuracy=accuracy, files=[res['file'][0]],
                additional_query=add_query
                )
        if len(res_) > 0:
            full_result.extend(res_)
            good_results.append(res)
    words.append(word_)  # word_ back to words to continue searching
    return full_result, good_results


def _find_word(word, filter_query, words_left, solr, accuracy=False, files=[""], limit=10000, additional_query=[]):
    """
    finds 'limit' entries of the word given
    @param accuracy: set it True to have only exact matches
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
