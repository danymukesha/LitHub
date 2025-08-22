black lithub.py
isort lithub.py
autopep8 --in-place --aggressive --aggressive lithub.py
autoflake --in-place --remove-unused-variables --remove-all-unused-imports lithub.py
autoflake lithub.py
