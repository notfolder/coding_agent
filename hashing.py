from mcp.server.fastmcp import FastMCP
import hashlib

# 「Hasher」という名前の FastMCP サーバーを生成
mcp = FastMCP(name="Hasher")

@mcp.tool()
def hash_sha256(text: str) -> str:
    """Calculate the SHA-256 hash of the input text.It is intended for use during file updates in workflows such as GitHub or GitLab,         where you need to verify or record the file’s SHA checksum as part of release version tracking.

    Args:
        text (str): The text to hash.

    Returns:
        str: The SHA-256 hash value.
    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string.")
    return hashlib.sha256(text.encode()).hexdigest()

if __name__ == "__main__":
    # stdio モードで起動
    mcp.run(transport="stdio")
