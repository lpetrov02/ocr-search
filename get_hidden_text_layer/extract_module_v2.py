from tqdm.notebook import tqdm
import sys
import djvu.decode
import mysql.connector
import MySQLdb.cursors
import sphinxapi


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


def index_word(word_tuple, words_info_, page_number, line_number, word_number):
    if isinstance(word_tuple, tuple):
        if len(word_tuple) == 0:
            return
        if word_tuple[0] == djvu.sexpr.Symbol('word'):
            coordinates_list = [str(word_tuple[i]) for i in range(1, 5)]
            word = word_tuple[5]
            words_info_.append((word, ','.join(coordinates_list), page_number, line_number, word_number))


def index_line(line_tuple, words_info_, page_number, line_number):
    if isinstance(line_tuple, tuple):
        if len(line_tuple) == 0:
            return
        if line_tuple[0] == djvu.sexpr.Symbol('line'):
            for i, word_tuple in enumerate(line_tuple[5:]):
                index_word(word_tuple, words_info_, page_number, line_number, i)


def index_page(sexpr, words_info_, page_number):
    if isinstance(sexpr, djvu.sexpr.ListExpression):
        if len(sexpr) == 0:
            return
        if sexpr.value[0] == djvu.sexpr.Symbol('page'):
            for i, line_tuple in enumerate(sexpr.value[5:]):
                index_line(line_tuple, words_info_, page_number, i)


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

    def index_text(self, djvu_path, words_info_, pages=[]):
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

            index_page(page.text.sexpr, words_info_, i)


def dump_text(djvu_path, text_file_path, pages=[]):
    text_file = open(text_file_path, 'w')
    context = Context()
    context.process(djvu_path, text_file, pages)


def dump_and_index_text(djvu_path, pages=[]):
    # Connecting to the database
    db = MySQLdb.connect(host="localhost", user="root", password="khinkali")
    mysql_cursor = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    index_exists = mysql_cursor.execute("SHOW DATABASES like 'TextIndex'")
    if index_exists:
        print("Index already_exists")
        return

    # If Index does not exist, we have to create a database and a table in this database
    mysql_cursor.execute("CREATE DATABASE TextIndex")
    text_index_db = mysql.connector.connect(  # Connecting to this new database
        host="localhost",
        user="root",
        password="khinkali",
        database="TextIndex"
    )

    text_index_cursor = text_index_db.cursor()
    text_index_cursor.execute(
        "CREATE TABLE OneWord ("
        "id INT AUTO_INCREMENT PRIMARY KEY, "
        "word VARCHAR(255), "
        "coordinates VARCHAR(20), "
        "page INT,"
        "line INT,"
        "number INT)"
    )

    context = Context()
    try:
        words_info = []
        context.index_text(djvu_path, words_info, pages)

        sql_insert_request = "INSERT INTO OneWord (word, coordinates, page, line, number) VALUES (%s, %s, %s, %s, %s)"
        text_index_cursor.executemany(sql_insert_request, words_info)
        text_index_db.commit()
        db.close()
    except Exception as e:
        raise Exception(e.args[0])


def clean_index():
    db = MySQLdb.connect(host="localhost", user="root", password="khinkali")
    mysql_cursor = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    mysql_cursor.execute("DROP DATABASE TextIndex")
    db.close()


def find_word(word, exactly):
    db = MySQLdb.connect(host="localhost", user="root", password="khinkali")
    mysql_cursor = db.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    index_exists = mysql_cursor.execute("SHOW DATABASES like 'TextIndex'")
    if index_exists and word != "":
        text_index_db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="khinkali",
            database="TextIndex"
        )
        text_index_cursor = text_index_db.cursor()

        if exactly:
            sql_request = f"SELECT * FROM OneWord WHERE word='{word}'"
        else:
            sql_request = f"SELECT * FROM OneWord WHERE word LIKE '%{word}%'"
        text_index_cursor.execute(sql_request)
        entries = text_index_cursor.fetchall()
        for entry in entries:
            print(entry)
    else:
        print("Database error")

    db.close()
