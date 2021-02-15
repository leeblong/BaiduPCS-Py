from typing import Optional, List, Dict, NamedTuple
from os import PathLike
from pathlib import Path
import pickle

from baidupcs_py.baidupcs import BaiduPCSApi, PcsUser
from baidupcs_py.common.path import join_path
from baidupcs_py.commands.env import ACCOUNT_DATA_PATH

from rich import print


class Account(NamedTuple):
    user: PcsUser

    # current working directory
    pwd: str = "/"
    encrypt_key: Optional[str] = None
    salt: Optional[str] = None

    def pcsapi(self) -> BaiduPCSApi:
        auth = self.user.auth
        assert auth, f"{self}.user.auth is None"
        return BaiduPCSApi(
            bduss=auth.bduss,
            stoken=auth.stoken,
            ptoken=auth.ptoken,
            cookies=auth.cookies,
            user_id=self.user.user_id,
        )

    @staticmethod
    def from_bduss(bduss: str, cookies: Dict[str, Optional[str]] = {}) -> "Account":
        api = BaiduPCSApi(bduss=bduss, cookies=cookies)
        user = api.user_info()
        return Account(user=user)


class AccountManager:
    """Account Manager

    Manage all accounts
    """

    def __init__(self, data_path: Optional[PathLike] = None):
        self._accounts: Dict[int, Account] = {}  # user_id (int) -> Account
        self._who: Optional[int] = None  # user_id (int)
        self._data_path = data_path

    @staticmethod
    def load_data(data_path: PathLike) -> "AccountManager":
        try:
            data_path = Path(data_path).expanduser()
            am = pickle.load(data_path.open("rb"))
            _compat_account_manager(am)
            return am
        except Exception:
            return AccountManager(data_path=data_path)

    @property
    def accounts(self) -> List[Account]:
        """All accounts"""

        return list(self._accounts.values())

    def set_encrypt_key(
        self, encrypt_key: Optional[str] = None, salt: Optional[str] = None
    ):
        """Set encryption key"""

        assert self._who, "No recent user"

        account = self._accounts.get(self._who)

        assert account

        account = account._replace(encrypt_key=encrypt_key, salt=salt)
        self._accounts[self._who] = account

    def cd(self, remotedir: str = "/"):
        """Change current working directory"""

        assert self._who, "No recent user"

        account = self._accounts.get(self._who)

        assert account

        pwd = join_path(account.pwd, remotedir)
        account = account._replace(pwd=pwd)
        self._accounts[self._who] = account

    @property
    def pwd(self) -> str:
        """Current working directory of recent user"""

        assert self._who, "No recent user"

        account = self._accounts.get(self._who)

        assert account

        return account.pwd

    def who(self, user_id: Optional[int] = None) -> Optional[Account]:
        """Return recent `Account`"""

        user_id = user_id or self._who
        if user_id:
            return self._accounts.get(user_id)
        else:
            return None

    def update(self, user_id: Optional[int] = None):
        """Update user_info"""

        user_id = user_id or self._who
        if user_id:
            account = self._accounts.get(user_id)
            if not account:
                return None

            api = account.pcsapi()
            user = api.user_info()

            self._accounts[user_id] = account._replace(user=user)

    def su(self, user_id: int):
        """Change recent user with `PcsUser.user_id`

        Args:
            who (int): `PcsUser.user_id`
        """

        assert user_id in self._accounts, f"No user {user_id}"

        self._who = user_id

    def useradd(self, user: PcsUser):
        """Add an user to data"""

        self._accounts[user.user_id] = Account(user=user)

    def userdel(self, user_id: int):
        """Delete a user

        Args:
            who (int): `PcsUser.user_id`
        """

        if user_id in self._accounts:
            del self._accounts[user_id]
        if user_id == self._who:
            self._who = None

    def save(self, data_path: Optional[PathLike] = None):
        """Serialize to local path"""

        data_path = data_path or self._data_path
        assert data_path, "No data path"

        data_path = Path(data_path).expanduser()
        if not data_path.parent.exists():
            data_path.parent.mkdir(parents=True)

        pickle.dump(self, open(data_path, "wb"))


def _compat_account_manager(am: AccountManager):
    """Update stored account manager to compat current version"""
    _compat_v0_5_9(am)


def _compat_v0_5_9(am: AccountManager):
    for user_id, account in am._accounts.items():
        old_products = account.user.products
        if isinstance(old_products, dict):  # type: ignore
            print(  # type: ignore
                "[i yellow]Update[/i yellow]: Transfer PcsUser format for ^v0.5.9: "
                f"user_id: {user_id}"
            )
            am.update(user_id)

    data_path = am._data_path
    if not data_path or not Path(data_path).exists():
        am._data_path = ACCOUNT_DATA_PATH

    am.save()
