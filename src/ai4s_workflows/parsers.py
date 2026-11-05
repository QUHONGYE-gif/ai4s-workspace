"""Parse the mock calculation's retrieved output into a provenance-tracked Dict."""

import json

from aiida.common.exceptions import NotExistent
from aiida.orm import Dict
from aiida.parsers.parser import Parser


class LightMPNNParser(Parser):
    """A missing or malformed result is a failed calculation, never a success."""

    def parse(self, **kwargs):
        try:
            retrieved = self.retrieved
        except NotExistent:
            return self.exit_codes.MOCK_RUNTIME_FAIL

        if "result.json" not in retrieved.base.repository.list_object_names():
            return self.exit_codes.MOCK_RUNTIME_FAIL

        try:
            with retrieved.open("result.json", "r") as handle:
                result = json.load(handle)
        except (ValueError, UnicodeError):
            return self.exit_codes.INVALID_RESULT_JSON

        if not isinstance(result, dict):
            return self.exit_codes.INVALID_RESULT_JSON

        self.out("result", Dict(dict=result))

