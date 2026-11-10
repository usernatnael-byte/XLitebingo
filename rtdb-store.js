const crypto = require('crypto');

function clone(value) {
    if (value === undefined || value === null) return value;
    return JSON.parse(JSON.stringify(value));
}

function cleanKey(value) {
    const key = String(value);
    if (/[.#$\[\]/]/.test(key)) throw new Error(`Invalid Realtime Database key: ${key}`);
    return key;
}

function makeSnapshot(id, value) {
    const exists = value !== null && value !== undefined;
    return {
        id,
        key: id,
        exists,
        val: () => exists ? clone(value) : null,
        data: () => exists ? clone(value) : undefined
    };
}

function createStore(database) {
    const root = database.ref('/');
    let transactionQueue = Promise.resolve();

    function refFor(collection, id) {
        return database.ref(`${cleanKey(collection)}/${cleanKey(id)}`);
    }

    class DocumentReference {
        constructor(collection, id) {
            this.collectionName = cleanKey(collection);
            this.id = id == null ? crypto.randomBytes(10).toString('hex') : cleanKey(id);
        }
        async get() {
            const snap = await refFor(this.collectionName, this.id).get();
            return makeSnapshot(this.id, snap.val());
        }
        async set(value, options = {}) {
            const ref = refFor(this.collectionName, this.id);
            if (options.merge) {
                await ref.transaction(current => ({ ...(current || {}), ...(clone(value) || {}) }));
            } else {
                await ref.set(clone(value));
            }
        }
        async update(value) {
            await refFor(this.collectionName, this.id).update(clone(value));
        }
        async delete() {
            await refFor(this.collectionName, this.id).remove();
        }
    }

    class CollectionReference {
        constructor(name) { this.name = cleanKey(name); }
        doc(id) { return new DocumentReference(this.name, id); }
        orderBy(field, direction = 'asc') { return new Query(this.name, field, direction, null); }
        async get() { return new Query(this.name, null, 'asc', null).get(); }
    }

    class Query {
        constructor(name, field, direction, max) {
            this.name = name; this.field = field; this.direction = direction; this.max = max;
        }
        orderBy(field, direction = 'asc') { return new Query(this.name, field, direction, this.max); }
        limit(max) { return new Query(this.name, this.field, this.direction, Number(max)); }
        async get() {
            const snap = await database.ref(this.name).get();
            const raw = snap.val() || {};
            let docs = Object.entries(raw).map(([id, value]) => makeSnapshot(id, value));
            if (this.field) {
                const field = this.field;
                docs.sort((a, b) => {
                    const av = a.data()?.[field] ?? 0;
                    const bv = b.data()?.[field] ?? 0;
                    const cmp = typeof av === 'number' && typeof bv === 'number'
                        ? av - bv : String(av).localeCompare(String(bv));
                    return this.direction === 'desc' ? -cmp : cmp;
                });
            }
            if (Number.isFinite(this.max)) docs = docs.slice(0, this.max);
            return { docs, size: docs.length, empty: docs.length === 0, forEach: fn => docs.forEach(fn) };
        }
    }

    async function runTransaction(callback) {
        let release;
        const previous = transactionQueue;
        transactionQueue = new Promise(resolve => { release = resolve; });
        await previous;
        try {
            const working = new Map();
            const touched = new Map();
            const tx = {
                async get(docRef) {
                    const path = `${docRef.collectionName}/${docRef.id}`;
                    if (!working.has(path)) {
                        const snap = await database.ref(path).get();
                        working.set(path, clone(snap.val()));
                    }
                    return makeSnapshot(docRef.id, working.get(path));
                },
                set(docRef, value, options = {}) {
                    const path = `${docRef.collectionName}/${docRef.id}`;
                    const current = working.get(path);
                    working.set(path, options.merge ? { ...(current || {}), ...(clone(value) || {}) } : clone(value));
                    touched.set(path, true);
                },
                update(docRef, value) {
                    const path = `${docRef.collectionName}/${docRef.id}`;
                    working.set(path, { ...(working.get(path) || {}), ...(clone(value) || {}) });
                    touched.set(path, true);
                },
                delete(docRef) {
                    const path = `${docRef.collectionName}/${docRef.id}`;
                    working.set(path, null);
                    touched.set(path, true);
                }
            };
            const result = await callback(tx);
            const updates = {};
            for (const path of touched.keys()) updates[path] = working.get(path);
            if (Object.keys(updates).length) await root.update(updates);
            return result;
        } finally {
            release();
        }
    }

    return {
        collection: name => new CollectionReference(name),
        runTransaction
    };
}

module.exports = createStore;
