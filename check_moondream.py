"""
check_moondream.py — standalone diagnostic. Tests engine.file_processor's
describe_image() directly against a real image, bypassing the browser UI
entirely, so you know immediately whether moondream/Ollama itself works.

Usage:
    python check_moondream.py path\\to\\some\\image.jpg
"""

import sys

from engine.file_processor import describe_image

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(r'Usage: python check_moondream.py path\to\some\image.jpg')
        sys.exit(1)

    image_path = sys.argv[1]

    print(f"Sending {image_path} to moondream via Ollama...")
    answer, error = describe_image(image_path, "Describe this image in detail.")

    if error:
        print("FAILED:")
        print(error)
    else:
        print("SUCCESS:")
        print(answer)