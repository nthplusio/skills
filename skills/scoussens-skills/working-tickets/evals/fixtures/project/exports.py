import csv
import io


def render(rows, delimiter=","):
    output = io.StringIO(newline="")
    if rows:
        output.write(delimiter.join(["name", "amount"]) + "\r\n")
        for row in rows:
            output.write(delimiter.join(map(str, row)) + "\r\n")
    return output.getvalue()
