"""Write the public Supabase browser configuration into the Pages artifact."""
from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> None:
    config = {
        "url": os.getenv("SUPABASE_URL", "").strip(),
        "anonKey": os.getenv("SUPABASE_ANON_KEY", "").strip(),
    }
    target = Path("docs/supabase-config.js")
    target.write_text(
        "window.COIN_RECOMAND_SUPABASE = Object.freeze("
        + json.dumps(config, ensure_ascii=False)
        + ");\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
