import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'blog.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        PRAGMA user_version = 1;

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#E8EDF0',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT DEFAULT '',
            category_id INTEGER,
            tags TEXT DEFAULT '',
            cover_image TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            featured INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS article_tags (
            article_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (article_id, tag_id),
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS footprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_url TEXT,
            location TEXT,
            description TEXT,
            date TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT,
            type TEXT CHECK(type IN ('article','tool')),
            note TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            image_url TEXT DEFAULT '',
            mood TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS inspirations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS media_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT CHECK(type IN ('music','anime')),
            title TEXT,
            subtitle TEXT,
            cover_url TEXT,
            link_url TEXT,
            status TEXT CHECK(status IN ('watching','watched','want')),
            episode TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        INSERT OR IGNORE INTO categories (id, name, description) VALUES (1, '默认分类', '默认文章分类');
    """)
    conn.commit()

    # Migration: add parent_id and sort_order to categories (tree structure)
    migration_tree_key = 'schema_v3_tree'
    tree_row = conn.execute("SELECT value FROM settings WHERE key=?", (migration_tree_key,)).fetchone()
    if not tree_row:
        try:
            conn.execute("ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL REFERENCES categories(id)")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE categories ADD COLUMN sort_order INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (migration_tree_key, datetime.now().isoformat()))
        conn.commit()

    # Migrate existing moments table (add image_url, mood if missing)
    try:
        conn.execute("ALTER TABLE moments ADD COLUMN image_url TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE moments ADD COLUMN mood TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()

    # Migration: remove CHECK constraints from media_items and collections
    # to allow custom type names
    from datetime import datetime as _dt
    migration_key = 'schema_v2'
    row = conn.execute("SELECT value FROM settings WHERE key=?", (migration_key,)).fetchone()
    if not row:
        # Migrate media_items
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS media_items_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT DEFAULT '',
                title TEXT,
                subtitle TEXT,
                cover_url TEXT,
                link_url TEXT,
                status TEXT DEFAULT '',
                episode TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            INSERT OR IGNORE INTO media_items_v2 SELECT * FROM media_items;
            DROP TABLE IF EXISTS media_items;
            ALTER TABLE media_items_v2 RENAME TO media_items;

            CREATE TABLE IF NOT EXISTS collections_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT,
                type TEXT DEFAULT '',
                note TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            INSERT OR IGNORE INTO collections_v2 SELECT * FROM collections;
            DROP TABLE IF EXISTS collections;
            ALTER TABLE collections_v2 RENAME TO collections;
        """)
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (migration_key, _dt.now().isoformat()))
        conn.commit()
    # Migrate existing articles: add featured column
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN featured INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.close()


# --- Article CRUD ---

def get_all_articles():
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        ORDER BY a.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_article(article_id):
    conn = get_db()
    row = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.id = ?
    """, (article_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_article(title, content, category_id, tags='', summary='', cover_image='', featured=0):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO articles (title, content, summary, category_id, tags, cover_image, featured)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (title, content, summary, category_id, tags, cover_image, featured))
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid

def get_featured_articles(limit=6):
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.featured = 1
        ORDER BY a.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_article(article_id, title, content, category_id, tags='', summary='', cover_image='', featured=0):
    conn = get_db()
    conn.execute("""
        UPDATE articles SET title=?, content=?, summary=?, category_id=?, tags=?, cover_image=?, featured=?,
        updated_at=datetime('now','localtime') WHERE id=?
    """, (title, content, summary, category_id, tags, cover_image, featured, article_id))
    conn.commit()
    conn.close()

def delete_article(article_id):
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE id=?", (article_id,))
    conn.commit()
    conn.close()

def search_articles(keyword):
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.title LIKE ? OR a.content LIKE ? OR a.tags LIKE ?
        ORDER BY a.created_at DESC
    """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Category CRUD ---

def get_all_categories():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM articles a WHERE a.category_id = c.id) as article_count,
            (SELECT COUNT(*) FROM categories cc WHERE cc.parent_id = c.id) as children_count
        FROM categories c ORDER BY c.sort_order ASC, c.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_category(name, description='', parent_id=None):
    conn = get_db()
    try:
        cur = conn.execute("INSERT INTO categories (name, description, parent_id) VALUES (?, ?, ?)",
                          (name, description, parent_id))
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return cid
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_category(category_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_category(category_id, name, description='', parent_id=None):
    conn = get_db()
    try:
        conn.execute("UPDATE categories SET name=?, description=?, parent_id=? WHERE id=?",
                     (name, description, parent_id, category_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def delete_category(category_id):
    conn = get_db()
    # Reparent children to the deleted category's parent
    cat = conn.execute("SELECT parent_id FROM categories WHERE id=?", (category_id,)).fetchone()
    parent_of_deleted = cat['parent_id'] if cat else None
    conn.execute("UPDATE categories SET parent_id=? WHERE parent_id=?", (parent_of_deleted, category_id))
    # Unlink articles
    conn.execute("UPDATE articles SET category_id=NULL WHERE category_id=?", (category_id,))
    conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
    conn.commit()
    conn.close()


# --- Category Tree Functions ---

def get_subcategories(parent_id):
    """Get direct children of a category."""
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM articles a WHERE a.category_id = c.id) as article_count,
            (SELECT COUNT(*) FROM categories cc WHERE cc.parent_id = c.id) as children_count
        FROM categories c WHERE c.parent_id = ?
        ORDER BY c.sort_order ASC, c.name
    """, (parent_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_ancestors(cat_id):
    """Get breadcrumb path from root to the given category (exclusive)."""
    conn = get_db()
    ancestors = []
    current = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    while current and current['parent_id'] is not None:
        parent = conn.execute("SELECT * FROM categories WHERE id=?", (current['parent_id'],)).fetchone()
        if parent:
            ancestors.insert(0, dict(parent))
            current = parent
        else:
            break
    conn.close()
    return ancestors

def get_category_tree():
    """Return full tree of categories as nested list.
    Each node: {id, name, description, article_count, children: [...]}
    """
    conn = get_db()
    all_cats = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM articles a WHERE a.category_id = c.id) as article_count
        FROM categories c ORDER BY c.sort_order ASC, c.name
    """).fetchall()
    conn.close()

    cats_dict = {}
    for c in all_cats:
        d = dict(c)
        d['children'] = []
        cats_dict[d['id']] = d

    roots = []
    for c in cats_dict.values():
        if c['parent_id'] is None:
            roots.append(c)
        else:
            parent = cats_dict.get(c['parent_id'])
            if parent:
                parent['children'].append(c)
            else:
                roots.append(c)  # orphan → treat as root

    return roots

def get_category_tree_flat():
    """Return flat list of categories with depth field for UI selectors."""
    conn = get_db()
    all_cats = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM articles a WHERE a.category_id = c.id) as article_count
        FROM categories c ORDER BY c.sort_order ASC, c.name
    """).fetchall()
    conn.close()

    cats_dict = {c['id']: dict(c) for c in all_cats}
    for c in cats_dict.values():
        c['depth'] = 0

    # Compute depth by walking up parent chain
    def compute_depth(cat):
        if cat['depth'] > 0 or cat['parent_id'] is None:
            return cat['depth']
        d = 0
        p = cat['parent_id']
        seen = set()
        while p is not None:
            if p in seen:
                break  # cycle safety
            seen.add(p)
            parent = cats_dict.get(p)
            if parent:
                d += 1
                p = parent['parent_id']
            else:
                break
        cat['depth'] = d
        return d

    for c in cats_dict.values():
        compute_depth(c)

    # Sort: roots first, then by parent
    sorted_cats = sorted(cats_dict.values(), key=lambda x: (x['depth'], x['sort_order'], x['name']))
    return sorted_cats

def move_article_category(article_id, category_id):
    """Move article to a different category."""
    conn = get_db()
    conn.execute("UPDATE articles SET category_id=? WHERE id=?", (category_id, article_id))
    conn.commit()
    conn.close()


# --- Tag CRUD ---

def get_all_tags():
    conn = get_db()
    rows = conn.execute("""
        SELECT t.*, COUNT(at.article_id) as article_count
        FROM tags t
        LEFT JOIN article_tags at ON t.id = at.tag_id
        GROUP BY t.id
        ORDER BY t.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_tag(name):
    conn = get_db()
    try:
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        conn.commit()
        tag_id = cur.lastrowid
        conn.close()
        return tag_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_tag(tag_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tags WHERE id=?", (tag_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def delete_tag(tag_id):
    conn = get_db()
    conn.execute("DELETE FROM article_tags WHERE tag_id=?", (tag_id,))
    conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
    conn.commit()
    conn.close()

def update_tag(tag_id, name):
    conn = get_db()
    try:
        conn.execute("UPDATE tags SET name=? WHERE id=?", (name, tag_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_articles_by_tag(tag_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        JOIN article_tags at ON a.id = at.article_id
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE at.tag_id = ?
        ORDER BY a.created_at DESC
    """, (tag_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_article_tags(article_id, tag_ids):
    """Replace all tags for an article with the given list of tag IDs."""
    conn = get_db()
    conn.execute("DELETE FROM article_tags WHERE article_id=?", (article_id,))
    for tid in tag_ids:
        conn.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?, ?)", (article_id, tid))
    conn.commit()
    conn.close()


# --- Footprint CRUD ---

def get_all_footprints():
    conn = get_db()
    rows = conn.execute("SELECT * FROM footprints ORDER BY sort_order ASC, date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_footprint(footprint_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM footprints WHERE id=?", (footprint_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_footprint(image_url, location, description, date, sort_order=0):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO footprints (image_url, location, description, date, sort_order)
        VALUES (?, ?, ?, ?, ?)
    """, (image_url, location, description, date, sort_order))
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return fid

def delete_footprint(footprint_id):
    conn = get_db()
    conn.execute("DELETE FROM footprints WHERE id=?", (footprint_id,))
    conn.commit()
    conn.close()

def update_footprint(footprint_id, image_url, location, description, date, sort_order=0):
    conn = get_db()
    conn.execute("""UPDATE footprints SET image_url=?, location=?, description=?, date=?, sort_order=? WHERE id=?""",
                 (image_url, location, description, date, sort_order, footprint_id))
    conn.commit()
    conn.close()


# --- Collection CRUD ---

def get_all_collections(type=None):
    conn = get_db()
    if type:
        rows = conn.execute("SELECT * FROM collections WHERE type=? ORDER BY created_at DESC", (type,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_collection(title, url, type, note=''):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO collections (title, url, type, note)
        VALUES (?, ?, ?, ?)
    """, (title, url, type, note))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid

def update_collection(collection_id, title, url, type, note=''):
    conn = get_db()
    conn.execute("UPDATE collections SET title=?, url=?, type=?, note=? WHERE id=?",
                 (title, url, type, note, collection_id))
    conn.commit()
    conn.close()

def delete_collection(collection_id):
    conn = get_db()
    conn.execute("DELETE FROM collections WHERE id=?", (collection_id,))
    conn.commit()
    conn.close()


# --- Moment CRUD ---

def get_all_moments():
    conn = get_db()
    rows = conn.execute("SELECT * FROM moments ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_moment(moment_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM moments WHERE id=?", (moment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_moment(content, image_url='', mood=''):
    conn = get_db()
    cur = conn.execute("INSERT INTO moments (content, image_url, mood) VALUES (?, ?, ?)",
                       (content, image_url, mood))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid

def update_moment(moment_id, content, image_url='', mood=''):
    conn = get_db()
    conn.execute("UPDATE moments SET content=?, image_url=?, mood=? WHERE id=?",
                 (content, image_url, mood, moment_id))
    conn.commit()
    conn.close()

def delete_moment(moment_id):
    conn = get_db()
    conn.execute("DELETE FROM moments WHERE id=?", (moment_id,))
    conn.commit()
    conn.close()


# --- Inspiration CRUD ---

def get_all_inspirations():
    conn = get_db()
    rows = conn.execute("SELECT * FROM inspirations ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_inspiration(inspiration_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM inspirations WHERE id=?", (inspiration_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_inspiration(content, tags=''):
    conn = get_db()
    cur = conn.execute("INSERT INTO inspirations (content, tags) VALUES (?, ?)", (content, tags))
    conn.commit()
    iid = cur.lastrowid
    conn.close()
    return iid

def update_inspiration(inspiration_id, content, tags=''):
    conn = get_db()
    conn.execute("UPDATE inspirations SET content=?, tags=? WHERE id=?",
                 (content, tags, inspiration_id))
    conn.commit()
    conn.close()

def delete_inspiration(inspiration_id):
    conn = get_db()
    conn.execute("DELETE FROM inspirations WHERE id=?", (inspiration_id,))
    conn.commit()
    conn.close()


# --- Media CRUD ---

def get_all_media(type=None):
    conn = get_db()
    if type:
        rows = conn.execute("SELECT * FROM media_items WHERE type=? ORDER BY sort_order ASC, created_at DESC", (type,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM media_items ORDER BY sort_order ASC, created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_media(type, title, subtitle='', cover_url='', link_url='', status='want', episode='', sort_order=0):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO media_items (type, title, subtitle, cover_url, link_url, status, episode, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (type, title, subtitle, cover_url, link_url, status, episode, sort_order))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid

def update_media(media_id, type, title, subtitle='', cover_url='', link_url='', status='', episode='', sort_order=0):
    conn = get_db()
    conn.execute("""UPDATE media_items SET type=?, title=?, subtitle=?, cover_url=?, link_url=?, status=?, episode=?, sort_order=? WHERE id=?""",
                 (type, title, subtitle, cover_url, link_url, status, episode, sort_order, media_id))
    conn.commit()
    conn.close()

def delete_media(media_id):
    conn = get_db()
    conn.execute("DELETE FROM media_items WHERE id=?", (media_id,))
    conn.commit()
    conn.close()


# --- Date-based article queries ---

def get_articles_by_date(date_str):
    """Get articles matching a specific date (YYYY-MM-DD)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, c.name as category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE date(a.created_at) = ?
        ORDER BY a.created_at DESC
    """, (date_str,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_article_counts_by_month(year, month):
    """Return per-day article counts for a given month. Returns {day: count}."""
    conn = get_db()
    rows = conn.execute("""
        SELECT strftime('%d', created_at) as day, COUNT(*) as count
        FROM articles
        WHERE strftime('%Y', created_at) = ? AND strftime('%m', created_at) = ?
        GROUP BY strftime('%d', created_at)
        ORDER BY day
    """, (str(year), f'{month:02d}')).fetchall()
    conn.close()
    return {r['day']: r['count'] for r in rows}
