with open('src/db/models.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if '__table_args__ = (' in line:
        if line.strip().endswith(',)'):
            new_lines[-1] = line.replace(',)', ', {"extend_existing": True})')
        elif line.strip().endswith(')'):
            new_lines[-1] = line.replace(')', ', {"extend_existing": True})')
    elif '__tablename__ =' in line:
        # Check if next lines have table_args
        has_args = False
        for j in range(i+1, min(i+5, len(lines))):
            if '__table_args__' in lines[j] or 'class ' in lines[j]:
                if '__table_args__' in lines[j]:
                    has_args = True
                break
        if not has_args:
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(f'{indent}__table_args__ = {{"extend_existing": True}}\n')

with open('src/db/models.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
