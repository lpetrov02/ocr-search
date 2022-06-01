import mysql.connector
import MySQLdb.cursors


sql_password = "khinkali"


class SolrStats:
    def __init__(self):
        self.db = MySQLdb.connect(host="localhost", user="root", password="khinkali")
        self.mysql_cursor = self.db.cursor(cursorclass=MySQLdb.cursors.DictCursor)

        self.mysql_cursor.execute("CREATE DATABASE IF NOT EXISTS IndexedFiles")
        self.index_db = mysql.connector.connect(host="localhost", user="root",
                                                password=sql_password, database="IndexedFiles")
        self.index_cursor = self.index_db.cursor()
        self.index_cursor.execute(
            "CREATE TABLE IF NOT EXISTS Files ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "file VARCHAR(255), recordings INT)")

    def add_words(self, file_name, n_words):
        self.index_cursor.execute(f"SELECT recordings FROM Files WHERE file='{file_name}'")
        recordings_number = self.index_cursor.fetchall()

        sql_request = "INSERT INTO Files (file, recordings) VALUES(%s, %s)"
        if len(recordings_number) == 0:
            self.index_cursor.execute(sql_request, (file_name, n_words))
        elif len(recordings_number) == 1:
            self.index_cursor.execute(sql_request, (file_name, recordings_number[0] + n_words))
        self.index_db.commit()

    def delete_from_index(self, files):
        if "" in files:
            self.index_cursor.execute("DELETE FROM Files")
        else:
            sql_request = "DELETE FROM Files WHERE file IN ('" + "', '".join(files) + "')"
            self.index_cursor.execute(sql_request)
        self.index_db.commit()

    def get_number_of_recordings(self, file_name):
        self.index_cursor.execute(f"SELECT recordings FROM Files WHERE file='{file_name}'")
        recordings_number = self.index_cursor.fetchall()
        if len(recordings_number) == 0:
            return 0
        else:
            return recordings_number[0]

    def get_indexed_files(self):
        self.index_cursor.execute("SELECT * FROM Files WHERE recordings > 0")
        res = self.index_cursor.fetchall()
        return res

    def close(self):
        self.index_db.close()
        self.db.close()