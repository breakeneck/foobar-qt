import os
import apsw

DB_NAME = 'db.sqlite3'

# import sqlite3
# connection: sqlite3.Connection
# db: sqlite3.Cursor

connection: apsw.Connection
db: apsw.Connection
# Cursor

def connect():
    global connection, db

    is_db_exists = True if os.path.exists(DB_NAME) else False

    # connection = None
    # try:
    connection = apsw.Connection(DB_NAME)
    # connection = sqlite3.connect(DB_NAME)
    db = connection.cursor()
    if not is_db_exists:
        print("Database and all tables will be created")
        return is_db_exists
    # except
    # except sqlite3.Error as e:
    #     print(e)

def drop():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)


class Model:
    @property
    def tableName(self):
        raise NotImplementedError("Please fill in table name")

    @property
    def pk(self):
        return 'id'

    def indexOf(self, attr):
        return list(self.__dict__.keys()).index(attr)

    def setAttrs(self, attrs):
        for index, attr in enumerate(self.__dict__):
            setattr(self, attr, attrs[index])

    @property
    def indexedAttrs(self):
        return []

    @staticmethod
    def get_values(row):
        return ['' for x in range(100)] if not row else row

    def get_field_type(self, attr):
        return type(getattr(self, attr)).__name__.replace('float', 'real').replace('str', 'text')

    def create_table(self):
        fields = []

        for attr in self.__dict__:
            if attr == 'id':
                fields.append('id integer PRIMARY KEY AUTOINCREMENT')
            else:
                is_pk = ' PRIMARY KEY' if attr == self.pk else ''
                fields.append(f'{attr} {self.get_field_type(attr)}{is_pk}')

        fields_str = ','.join(fields)
        db.execute(f'CREATE TABLE IF NOT EXISTS {self.tableName} ({fields_str})')

        self.create_indexes()

        # connection.commit()

    def create_indexes(self):
        for attr in self.indexedAttrs:
            db.execute(f"CREATE INDEX IF NOT EXISTS {attr}_{self.tableName} ON {self.tableName}({attr});")

    def insert(self):
        attributes_list = []
        values = []
        for attr in self.__dict__:
            if attr == self.pk:
                continue
            attributes_list.append(attr)
            values.append(self.__dict__[attr])

        question_marks = ','.join(['?' for x in range(len(values))])
        attributes = ','.join(attributes_list)

        try:
            lastrowid = db.execute(f'INSERT INTO {self.tableName}({attributes}) VALUES({question_marks})', values)
            # connection.commit()
        except Exception as e:
            print('Insert error: ' + str(e) + ' Attributes: ' + str(self.__dict__))

        return lastrowid

    def update(self):
        attributes_list = []
        values = []
        for attr in self.__dict__:
            if attr == self.pk:
                continue
            attributes_list.append(attr + ' = ?')
            values.append(self.__dict__[attr])
        attributes = ','.join(attributes_list)

        # print(f'UPDATE {self.tableName} SET {attributes} WHERE id = {self.__dict__[self.pk]}')
        # print(values)

        if not db:
            connect()
        db.execute(f'UPDATE {self.tableName} SET {attributes} WHERE id = {self.__dict__[self.pk]}', values)
        # connection.commit()

    def updateAttr(self, attr):
        db.execute(f'UPDATE {self.tableName} SET {attr} = ? WHERE id = {self.__dict__[self.pk]}', [self.__dict__[attr]])
        # connection.commit()

    def load(self, values):
        for n, attr in enumerate(self.__dict__):
            setattr(self, attr, values[n])
        return self
