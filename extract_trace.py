import codecs
import re

with codecs.open('test_full.log', 'r', 'utf-16') as f:
    log_content = f.read()

tracebacks = []
current_tb = []
in_tb = False

for line in log_content.splitlines():
    if line.startswith('Traceback'):
        in_tb = True
        current_tb.append(line)
    elif in_tb:
        if line.startswith('2026') or line.strip() == '':
            if current_tb:
                tracebacks.append('\n'.join(current_tb))
                current_tb = []
            in_tb = False
        else:
            current_tb.append(line)

with open('traces.txt', 'w', encoding='utf-8') as f:
    for tb in tracebacks:
        f.write(tb + '\n\n')
