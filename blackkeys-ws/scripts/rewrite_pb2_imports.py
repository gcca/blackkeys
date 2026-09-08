import pathlib

GEN_DIR = pathlib.Path("blackkeys/gen/v1")


def RewriteImports() -> None:
    for path in GEN_DIR.glob("*.py"):
        text = path.read_text()
        rewritten = text.replace("from v1 import ", "from blackkeys.gen.v1 import ")
        if rewritten != text:
            path.write_text(rewritten)


if __name__ == "__main__":
    RewriteImports()
