import { readFileSync, writeFileSync } from 'node:fs';

const names = new Map();

function add(noun, symbol) {
    if (!/^[а-яё-]+$/u.test(noun) || !symbol || symbol === noun ||
        !/^(?:\p{L}+|[^\p{L}\p{N}\s])$/u.test(symbol)) return;
    if (!names.has(symbol)) names.set(symbol, new Set());
    names.get(symbol).add(noun);
}

for (const unit of Intl.supportedValuesOf('unit')) {
    const label = (unitDisplay) => new Intl.NumberFormat('ru', {style: 'unit', unit, unitDisplay})
        .formatToParts(1).find(part => part.type === 'unit').value;
    for (const style of ['short', 'narrow']) add(label('long'), label(style));
}

if (process.argv[3]) {
    const units = JSON.parse(readFileSync(process.argv[3], 'utf8')).main.ru.units;
    for (const [unit, entry] of Object.entries(units.long)) {
        const noun = /^\{0\}\s+([а-яё-]+)$/u.exec(entry['unitPattern-count-one'] || '')?.[1];
        if (!noun) continue;
        for (const style of ['short', 'narrow']) {
            const pattern = units[style][unit]?.['unitPattern-count-one'] || '';
            const symbol = /^\{0\}\s*(\S+)$/u.exec(pattern)?.[1];
            add(noun, symbol);
        }
    }
}

const rows = [...names].filter(([, words]) => words.size === 1)
    .map(([symbol, words]) => symbol + '\t' + [...words][0]).sort();
writeFileSync(process.argv[2], rows.join('\n') + '\n');
