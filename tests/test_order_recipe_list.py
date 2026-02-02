import unittest

from autopkg_wrapper.utils.recipe_ordering import order_recipe_list


class TestOrderRecipeList(unittest.TestCase):
    def test_orders_by_type_then_alpha(self):
        recipes = [
            "ExampleApp.self_service.jamf",
            "ExampleApp.upload.jamf",
            "ExampleApp.auto_install.jamf",
            "AnotherApp.upload.jamf",
        ]
        ordered = order_recipe_list(
            recipe_list=recipes,
            order=["upload.jamf", "auto_install.jamf", "self_service.jamf"],
        )
        self.assertEqual(
            ordered,
            [
                "AnotherApp.upload.jamf",
                "ExampleApp.upload.jamf",
                "ExampleApp.auto_install.jamf",
                "ExampleApp.self_service.jamf",
            ],
        )

    def test_strips_known_extensions(self):
        recipes = [
            "Foo.upload.jamf.recipe",
            "Bar.upload.jamf.recipe.yaml",
        ]
        ordered = order_recipe_list(recipe_list=recipes, order=["upload.jamf"])
        self.assertEqual(ordered, ["Bar.upload.jamf", "Foo.upload.jamf"])

    def test_handles_order_string_from_env_default(self):
        recipes = [
            "A.auto_install.jamf",
            "B.upload.jamf",
            "C.self_service.jamf",
        ]
        ordered = order_recipe_list(
            recipe_list=recipes,
            order="upload.jamf,auto_install.jamf,self_service.jamf",
        )
        self.assertEqual(
            ordered,
            [
                "B.upload.jamf",
                "A.auto_install.jamf",
                "C.self_service.jamf",
            ],
        )

    def test_partial_type_matching_with_intermediate_segments(self):
        recipes = [
            "Google_Chrome.auto_install.jamf",
            "Google_Chrome.epz.auto_install.jamf",
            "Google_Chrome.epz.auto_update.jamf",
            "Google_Chrome.eux.auto_update.jamf",
            "Google_Chrome.eux.self_service.jamf",
            "Google_Chrome.self_service.jamf",
            "Google_Chrome.upload.jamf",
        ]

        ordered = order_recipe_list(
            recipe_list=recipes,
            order=["upload", "auto_update", "auto_install", "self_service"],
        )

        self.assertEqual(
            ordered,
            [
                "Google_Chrome.upload.jamf",
                "Google_Chrome.epz.auto_update.jamf",
                "Google_Chrome.eux.auto_update.jamf",
                "Google_Chrome.auto_install.jamf",
                "Google_Chrome.epz.auto_install.jamf",
                "Google_Chrome.eux.self_service.jamf",
                "Google_Chrome.self_service.jamf",
            ],
        )


if __name__ == "__main__":
    unittest.main()
