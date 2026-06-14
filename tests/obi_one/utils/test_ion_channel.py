from pathlib import Path

from obi_one.utils.ion_channel import get_suffix_from_mod_file

DATA_FOLDER_PATH = Path(__file__).parent.parent.parent / "test_data"
IC_MOD_FILE_PATH = DATA_FOLDER_PATH / "TC_iT_Des98.mod"


def test_get_suffix_from_mod_file():
    suffix = get_suffix_from_mod_file(IC_MOD_FILE_PATH)
    assert suffix == "TC_iT_Des98"
