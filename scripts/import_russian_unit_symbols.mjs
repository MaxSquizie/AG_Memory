import { writeFileSync } from 'node:fs';

const names = new Map();
for (const unit of Intl.supportedValuesOf('unit')) {
    const label = (unitDisplay) => new Intl.NumberFormat('ru', {style: 'unit', unit, unitDisplay})
        .formatToParts(1).find(part => part.type === 'unit').value;
    const noun = label('long');
    if (!/^[а-яё-]+$/u.test(noun)) continue;
    for (const style of ['short', 'narrow']) {
        const symbol = label(style);
        if (symbol === noun || !/^(?:\p{L}+|[^\p{L}\p{N}\s])$/u.test(symbol)) continue;
        if (!names.has(symbol)) names.set(symbol, new Set());
        names.get(symbol).add(noun);
    }
}
const rows = [...names].filter(([, words]) => words.size === 1)
    .map(([symbol, words]) => symbol + '\t' + [...words][0]).sort();
writeFileSync(process.argv[2], rows.join('\n') + '\n');
