# -*- coding: utf-8 -*-

""" pyKwalify - Core.py """

__author__ = 'Grokzen <grokzen@gmail.com>'

# python std lib
import re
import os
import sys
import json

# python std logging
import logging
Log = logging.getLogger(__name__)

# pyKwalify imports
from .rule import Rule
from .types import *
from .errors import *

# 3rd party imports
import yaml

class Core(object):
    """ Core class of pyKwalify """

    def __init__(self, source_file = None, schema_file = None, source_data = None, schema_data = None):
        Log.debug("source_file: %s" % source_file)
        Log.debug("schema_file: %s" % schema_file)
        Log.debug("source_data: %s" % source_data)
        Log.debug("schema_data: %s" % schema_data)

        self.source = None
        self.schema = None

        if source_file is not None:
            if not os.path.exists(source_file):
                raise CoreError("Provided source_file do not exists on disk")
                
            with open(source_file, "r") as stream:
                if source_file.endswith(".json"):
                    self.source = json.load(stream)
                elif source_file.endswith(".yaml"):
                    self.source = yaml.load(stream)
                else:
                    raise CoreError("Unable to load source_file. Unknown file format.")

        if schema_file is not None:
            if not os.path.exists(schema_file):
                raise CoreError("Provided source_file do not exists on disk")

            with open(schema_file, "r") as stream:
                if schema_file.endswith(".json"):
                    self.schema = json.load(stream)
                elif schema_file.endswith(".yaml"):
                    self.schema = yaml.load(stream)
                else:
                    raise CoreError("Unable to load schema_file. Unknown file format.")

        # Nothing was loaded so try the source_data variable
        if self.source is None:
            self.source = source_data
        if self.schema is None:
            self.schema = schema_data

        # Test if anything was loaded
        if self.source is None:
            raise CoreError("No source file/data was loaded")
        if self.schema is None:
            raise CoreError("No schema file/data was loaded")

        # Everything now is valid loaded

    def run_core(self):
        errors = self._start_validate(self.source)
        if errors is None or len(errors) == 0:
            Log.info("validation.valid")
        else:
            Log.error("validation.invalid")
            Log.error(" - All found errors -")
            Log.error(errors)
            raise Exception("validation.invalid : %s" % errors)

    def _start_validate(self, value = None):
        path = ""
        errors = []
        done = []
        Log.debug("Building root rule object")
        root_rule = Rule(schema = self.schema)
        Log.debug("Done building root rule")

        self._validate(value, root_rule, path, errors, done)

        return errors

    def _validate(self, value, rule, path, errors, done):
        Log.debug("Rule: %s" % rule._type)
        Log.debug("Seq: %s" % rule._sequence)
        Log.debug("Map: %s" % rule._mapping)

        if rule._required and self.source is None:
            raise CoreError("required.novalue")

        n = len(errors)
        if rule._sequence is not None:
            self._validate_sequence(value, rule, path, errors, done = None)
        elif rule._mapping is not None:
            self._validate_mapping(value, rule, path, errors, done = None)
        else:
            self._validate_scalar(value, rule, path, errors, done = None)

        if len(errors) != n:
            return 

    def _validate_sequence(self, value, rule, path, errors = [], done = None):
        Log.debug("Validate sequence")
        Log.debug(" * %s" % value)
        Log.debug(" * %s" % rule)
        Log.debug(" * %s" % rule._type)

        assert isinstance(rule._sequence, list), "sequence not of list type"
        assert len(rule._sequence) == 1, "only 1 item allowed in sequence rule"
        if value is None:
            return

        r = rule._sequence[0]
        i = 0
        for item in value:
            # Validate recursivley
            self._validate(item, r, "%s/%s" % (path, i), errors, done)

        if rule._type == "map":
            mapping = rule._mapping
            unique_keys = []
            for k, rule in mapping.items():
                Log.debug("Key: %s" % k)
                Log.debug("Rule: %s" % rule)

                if rule._unique or rule._ident:
                    unique_keys.append(k)

            if len(unique_keys) > 0:
                for k, v in unique_keys.items():
                    table = {}
                    j = 0
                    for K, V in value.items():
                        val = V[v]
                        if val is None:
                            continue
                        if val in table:
                            curr_path = path + "/" + j + "/" + Key
                            prev_path = path + "/" + table[val] + "/" + key
                            errors.append("value.notunique")

        elif rule._unique:
            Log.debug(" - validate sequence test unique")
            table = {}
            j = 0
            for val in value:
                if val is None:
                    continue
                if val in table:
                    curr_path = path + "/" + j
                    prev_path = path + "/" + table[val]
                    errors.append("value.notunique")
                else:
                    table[val] = j

    def _validate_mapping(self, value, rule, path, errors = [], done = None):
        Log.debug("Validate mapping")
        Log.debug(" + %s" % value)
        Log.debug(" + %s" % rule)
        Log.debug(" + %s" % rule._type)
        Log.debug(rule._sequence)
        Log.debug(rule._mapping)

        assert isinstance(rule._mapping, dict), "mapping is not a valid dict object"
        if value is None:
            return

        m = rule._mapping
        for k, rule in m.items():
            if rule._required and k not in value:
                errors.append("required.nokey")

        for k, v in value.items():
            rule = m.get(k, None)
            if rule is None:
                errors.append("key.undefined")
            else:
                # validate recursively
                self._validate(v, rule, "%s/%s" % (path, k), errors, done)

    def _validate_scalar(self, value, rule, path, errors = [], done = None):
        Log.debug("Validate scalar")
        Log.debug(" # %s" % value)
        Log.debug(" # %s" % rule)
        Log.debug(" # %s" % rule._type)

        assert rule._sequence is None, "found sequence when validating for scalar"
        assert rule._mapping is None, "found mapping when validating for scalar"

        if rule._assert is not None:
            pass # TODO: implement assertion prolly

        if rule._enum is not None:
            if value not in rule._enum:
                errors.append("enum.notexists")

        if value is None:
            return

        if rule._pattern is not None:
            res = re.match(rule._pattern, str(value) )
            if res is None: # Not matching
                errors.append("pattern.unmatch")

        if rule._range is not None:
            assert isScalar(value), "value is not a valid scalar"

            r = rule._range
            if r.get("max", None) is not None and r["max"] < value:
                errors.append("range.toolarge")
            if r.get("min", None) is not None and r["min"] > value:
                errors.append("range.toosmall")
            if r.get("max-ex", None) is not None and r["max-ex"] <= value:
                errors.append("range.tolarge-ex")
            if r.get("min-ex", None) is not None and r["min-ex"] >= value:
                errors.append("range.toosmall-ex")

        if rule._length is not None:
            assert isinstance(value, str), "value is not a valid string type"

            l = rule._length
            L = len(value)

            if l.get("max", None) is not None and l["max"] < L:
                errors.append("length.toolong")
            if l.get("min", None) is not None and l["min"] > L:
                errors.append("length.tooshort")
            if l.get("max-ex", None) is not None and l["max-ex"] <= L:
                errors.append("length.toolong-ex")
            if l.get("min-ex", None) is not None and l["min-ex"] >= L:
                errors.append("length.tooshort-ex")

        self._validate_scalar_type(value, rule._type, errors)

    def _validate_scalar_type(self, value, t, errors):
        Log.debug(type(value) )

        if t == "str":
            if not isinstance(value, str):
                errors.append("Value: %s is not of type 'str'" % value)
        elif t == "int":
            if not isinstance(value, int):
                errors.append("Value: %s is not of type 'int'" % value)
        elif t == "bool":
            if not isinstance(value, bool):
                errors.append("Value: %s is not of type 'bool'" % value)
        else:
            raise Exception("Unknown type check")