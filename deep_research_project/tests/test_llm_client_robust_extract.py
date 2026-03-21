import unittest
from pydantic import BaseModel, ValidationError
from typing import List
from unittest.mock import MagicMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class RequiredFieldModel(BaseModel):
    name: str

class ListFieldModel(BaseModel):
    items: List[str]

class NestedItem(BaseModel):
    id: int
    data: str

class NestedListModel(BaseModel):
    nested: List[NestedItem]

class TestLLMClientRobustExtract(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.ENABLE_CACHING = False
        self.client = LLMClient(self.mock_config)

    def test_robust_json_extract_validation_error(self):
        """
        Verify that a ValueError is raised when extraction fails and
        a minimal model cannot be created because of required fields.
        """
        text = "This is some text without JSON"
        # RequiredFieldModel requires 'name', but min_data will be empty {}
        with self.assertRaises(ValueError) as cm:
            self.client._robust_json_extract(text, RequiredFieldModel)

        self.assertIn("Could not generate RequiredFieldModel even with robust extraction", str(cm.exception))

    def test_robust_json_extract_minimal_success(self):
        """
        Verify that if the model has a list field, it returns a minimal
        instance with an empty list when extraction fails.
        """
        text = "This is some text without JSON"
        # ListFieldModel will have min_data = {'items': []} which is valid
        result = self.client._robust_json_extract(text, ListFieldModel)
        self.assertIsInstance(result, ListFieldModel)
        self.assertEqual(result.items, [])

    def test_partial_model_recovery_success(self):
        """
        Verify that _partial_model_recovery can filter out invalid items
        in a list of BaseModels.
        """
        data = {
            "nested": [
                {"id": 1, "data": "valid"},
                {"id": "invalid", "data": "oops"}, # Should be filtered out
                {"id": 2, "data": "also valid"}
            ]
        }

        result = self.client._partial_model_recovery(data, NestedListModel)
        self.assertIsInstance(result, NestedListModel)
        self.assertEqual(len(result.nested), 2)
        self.assertEqual(result.nested[0].id, 1)
        self.assertEqual(result.nested[1].id, 2)

    def test_partial_model_recovery_last_resort(self):
        """
        Verify the last resort path in _partial_model_recovery.
        If even cleaning lists doesn't help, it tries model_validate({}).
        """
        # A model where 'name' is required and not a list
        data = {"name": 123} # name should be str, but let's say it fails for some reason
        # We need a model where partial recovery still fails.
        # RequiredFieldModel requires 'name'.

        # If we pass data that is invalid for RequiredFieldModel
        # _partial_model_recovery will see it's not a list field,
        # so it won't clean it.
        # Then it calls model_validate(cleaned_data) which will fail.
        # Then it calls model_validate({}) which will also fail for RequiredFieldModel.

        # To test the last resort path actually *returning* something,
        # we need a model where {} is valid.
        class OptionalFieldModel(BaseModel):
            opt: str = "default"

        data = {"opt": 123} # Invalid type
        result = self.client._partial_model_recovery(data, OptionalFieldModel)
        self.assertIsInstance(result, OptionalFieldModel)
        self.assertEqual(result.opt, "default")

    def test_robust_json_extract_list_match(self):
        """
        Verify that it can extract a JSON list and assign it to a list field in the model.
        """
        text = 'Some text and then ["a", "b", "c"]'
        result = self.client._robust_json_extract(text, ListFieldModel)
        self.assertIsInstance(result, ListFieldModel)
        self.assertEqual(result.items, ["a", "b", "c"])

if __name__ == "__main__":
    unittest.main()
