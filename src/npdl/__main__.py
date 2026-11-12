"""允许通过 ``python -m npdl`` 运行。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
