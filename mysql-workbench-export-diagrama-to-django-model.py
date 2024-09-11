# MySQL Workbench Plugin
# <description>
# Written in MySQL Workbench 8.0.36
# Author: Naylor Garcia Bachiega
# https://github.com/naylor

from wb import *
import grt
import mforms
import re
import unicodedata

ModuleInfo = DefineModule("djangoModel", author="Bachiega, Naylor G.", version="1.0.0", description="Generate Export to Django Model")

# This plugin takes no arguments
@ModuleInfo.plugin("export.djangoModel", caption="Generate Export to Django Model", description="description", input=[wbinputs.currentDiagram()], pluginMenu="Utilities")
@ModuleInfo.export(grt.INT, grt.classes.db_Catalog)

def djangoModel(diagram):
    newline = "\n"
    yml = ""
    tables = []

    for figure in diagram.figures:
        table = TableSkeleton()
        col_count = 0
        M2M = 0
        uniqueReferences = []

        for column in figure.table.columns:
            current_column = ColumnSkeleton()
            current_column.name = convergeName(column.name)
            current_column.orig_name = convergeName(column.name)
            current_column.type = djangoTypes(column.simpleType)

            # Assignments with default values
            current_column.length = max(0, column.length)
            current_column.precision = max(0, column.precision)
            current_column.scale = max(0, column.scale)
            current_column.required = column.isNotNull == 1
            current_column.autoIncrement = column.autoIncrement == 1

            # Set default value
            if column.defaultValue:
                current_column.default = column.defaultValue.strip("'")

            # Primary key
            if any(index.indexType == "PRIMARY" and any(ic.referencedColumn and ic.referencedColumn.name == column.name for ic in index.columns)
                   for index in figure.table.indices):
                current_column.primaryKey = True

            # Foreign key
            for foreignKey in figure.table.foreignKeys:
                foreignKeyColumn = foreignKey.columns[0]
                foreignKeyReferencedColumn = foreignKey.referencedColumns[0]

                if foreignKeyColumn.name == column.name:
                    current_column.foreignTable = convergeName(foreignKey.referencedTable.name)
                    current_column.foreignReference = convergeName(foreignKeyReferencedColumn.name)

                    if current_column.primaryKey and foreignKey.many != 1:
                        current_column.oneToOne = True

                    current_column.onDelete = {
                        "SET NULL": "SET_NULL",
                        "CASCADE": "CASCADE",
                        "NO ACTION": "RESTRICT",
                        "RESTRICT": "RESTRICT"
                    }.get(foreignKey.deleteRule, "RESTRICT")

                    if foreignKey.many == 1:
                        M2M = 1
                        uniqueReferences.append(convergeName(column.name))

            col_count += 1

            # Indexes
            for index in figure.table.indices:
                if index.name == column.name:
                    if index.indexType == "INDEX":
                        current_column.index = True
                    if index.indexType == "UNIQUE":
                        current_column.unique = True

            # Setting the second field as self in the model
            # The first one was not added to avoid using the ID
            if col_count == 2:
                table.addSelf = convergeName(column.name)

            table.name = convergeName(figure.table.name)
            current_column.obj_count = col_count
            table.M2M = M2M
            table.uniqueReferences = uniqueReferences
            table.columns.append(current_column)

        tables.append(table)

    # Django Model generation
    yml = (
        "#Model generated by the Generate Export to Django Model Plugin\n"
        "#Created by Naylor Garcia Bachiega\n"
        "#https://github.com/naylor\n\n"
        "from django.db import models\n\n"
    )

    # Sorts to process tables without relationships first
    tables = reorderTables(tables)
    for table in tables:
        yml += table.makeDjangoModel()

    mforms.Utilities.set_clipboard_text(yml)
    mforms.App.get().set_status_text("Documentation generated into the clipboard. Paste it to your editor.")

    return 0


class TableSkeleton:
    def __init__(self):
        self.name = None,
        self.addSelf = None
        self.columns = []
        self.M2M = 0
        self.uniqueReferences = []

    def makeDjangoModel(self):
        newline = "\n"
        tab = "    "
        yml = ""

        # Convert table name to Django model class name
        yml += f"class {self.name}(models.Model):" + newline

        for column in self.columns:
            field_str = column.getDjangoStrings(self)
            if field_str:
                yml += tab + field_str + newline
        
        yml = yml + newline
        return yml


class ColumnSkeleton:
    def __init__(self):
        self.obj_count = 0
        self.name = None
        self.orig_name = None
        self.required = False
        self.primaryKey = False
        self.autoIncrement = False
        self.type = None
        self.length = 0
        self.default = None
        self.sequence = None
        self.index = False
        self.oneToOne = False
        self.foreignTable = None
        self.foreignReference = None
        self.onDelete = None
        self.isCulture = False
        self.precision = 0
        self.scale = 0
        self.unique = False

    def getDjangoStrings(self, table):
        sep = ", "
        newline = "\n"
        tab = "    "
        yml = f"{self.name} = models."

        # Adds ForeignKey or OneToOneField
        yml += self._build_fk_field(sep)

        # Finalizes FK if applicable
        if self.foreignTable is not None:
            yml = yml.rstrip(sep) + ")"
            yml += self._add_meta_and_str_method(table, newline, tab)
            return yml

        # Adds common field parameters
        yml += self._build_common_fields(sep)
        yml = yml.rstrip(sep) + ")"

        # Adds __str__ and Unique Together
        yml += self._add_meta_and_str_method(table, newline, tab)

        return yml

    def _build_fk_field(self, sep):
        FK = "OneToOneField" if self.oneToOne else "ForeignKey"
        yml = ""

        if self.foreignTable:
            yml += f"{FK}('{self.foreignTable}'"

            if self.foreignReference:
                yml += f", to_field='{self.foreignReference}'"

            if self.onDelete:
                yml += f", on_delete=models.{self.onDelete}"
                if self.onDelete == "SET_NULL":
                    yml += ", null=True"

            yml += sep

        return yml

    def _build_common_fields(self, sep):
        if self.autoIncrement:
            self.type = "AutoField"

        yml = f"{self.type}("

        if self.length:
            yml += f"max_length={self.length}{sep}"

        if not self.required:
            yml += f"blank=True{sep}"

        if self.precision:
            yml += f"decimal_places={self.precision}{sep}"
            if self.type == "DecimalField":
                self.scale = 10

        if self.scale:
            yml += f"max_digits={self.scale}{sep}"

        if self.primaryKey:
            yml += f"primary_key=True{sep}"

        if self.default and self.default != "NULL" and self.default != "now()":
            yml += f"default='{self.default}'{sep}"

        if self.index:
            yml += f"db_index=True{sep}"

        if self.unique:
            yml += f"unique=True{sep}"

        if self.type == "DateTimeField":
            if self.name == "created_at":
                yml += f"auto_now_add=True{sep}"
            elif self.name == "updated_at":
                yml += f"auto_now=True{sep}"
            
        if self.default == "now()":
                yml += f"auto_now=True{sep}"

        return yml

    def _add_meta_and_str_method(self, table, newline, tab):
        yml = ""

        # Adds the __str__ method if applicable
        if self.obj_count == len(table.columns) and table.addSelf:
            yml += newline * 2 + tab + "def __str__(self):" + newline
            yml += tab * 2 + f'return f"{{self.{table.addSelf}}}"'

        # Adds Unique Together for ManyToMany relationships
        if table.M2M and self.obj_count == len(table.columns):
            yml += newline * 2 + tab + "class Meta:" + newline
            yml += tab * 2 + "unique_together = (("
            yml += ", ".join(f"'{ref}'" for ref in table.uniqueReferences) + "),)"

        return yml



def reorderTables(tables):
    # Using list comprehensions to filter and sort tables
    no_m2m_tables = [table for table in tables if table.M2M == 0]
    m2m_tables = [table for table in tables if table.M2M == 1]

    # Merges the sorted lists
    return no_m2m_tables + m2m_tables


def convergeName(s):
    # Removes accents and Latin characters
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
    
    # Keeps only alphanumeric characters and the separators _ and .
    s = re.sub(r'[^a-zA-Z0-9._]', '', s).lower()
    
    # Capitalizes the initial letter after _ or .
    s = re.sub(r'[_\.](\w)', lambda match: match.group(1).upper(), s)
    
    # Removes remaining dashes and periods
    s = s.replace('_', '').replace('.', '')
    
    return s


def djangoTypes(columnType):
    if columnType is None:
        return "UNKNOWN"

    type_mapping = {
        "INT": "IntegerField",
        "MEDIUMINT": "IntegerField",
        "TINYINT": "IntegerField",
        "SMALLINT": "SmallIntegerField",
        "BIGINT": "BigIntegerField",
        "DECIMAL": "DecimalField",
        "DATETIME": "DateTimeField",
        "TIMESTAMP": "DateTimeField",
        "DATE": "DateField",
        "TIME": "TimeField",
        "BOOL": "BooleanField",
        "FLOAT": "FloatField",
        "DOUBLE": "FloatField",
        "TINYTEXT": "CharField",
        "VARCHAR": "CharField",
        "CHAR": "CharField",
        "TEXT": "TextField",
        "MEDIUMTEXT": "TextField",
        "LONGTEXT": "TextField"
    }

    return type_mapping.get(columnType.name, "NOT_FOUND")
