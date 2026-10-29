"""Create new private LinkedIn directories; never change existing ACLs."""
from pathlib import Path
import sys

from linkedin_mcp_server.private_state import harden_created_directory
from linkedin_mcp_server.windows_acl import verify_ancestry_cannot_be_replaced, verify_owner_only


def create_private(path: Path):
    # Python 3.12.4+ creates Windows mode-0700 directories with restricted ACLs.
    # Existing roots are verified only, including their ancestors and owner.
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        harden_created_directory(path)
    verify_ancestry_cannot_be_replaced(path)
    verify_owner_only(path, directory=True)


def prepare(root: Path):
    create_private(root)
    create_private(root / "installer")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
