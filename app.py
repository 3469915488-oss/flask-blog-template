import os
import re
import json
import markdown
import urllib.request
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort, session
from werkzeug.utils import secure_filename
from models import init_db, get_all_articles, get_article, create_article, update_article, delete_article, search_articles, get_featured_articles, get_all_categories, get_category, create_category, update_category, delete_category, get_all_tags, create_tag, update_tag, get_tag, delete_tag, get_articles_by_tag, get_all_footprints, get_footprint, create_footprint, update_footprint, delete_footprint, get_all_collections, create_collection, update_collection, delete_collection, get_all_moments, get_moment, create_moment, update_moment, delete_moment, get_all_inspirations, get_inspiration, create_inspiration, update_inspiration, delete_inspiration, get_all_media, create_media, update_media, delete_media, get_article_counts_by_month, get_articles_by_date, get_subcategories, get_ancestors, get_category_tree, get_category_tree_flat, move_article_category

app = Flask(__name__)
app.secret_key = os.environ.get('BLOG_SECRET_KEY', 'change-to-a-random-secret-key')
MOMENT_PASSWORD = os.environ.get('BLOG_MOMENT_PASSWORD', 'your-password-here')


def strip_tags(html):
    """Remove HTML tags from string."""
    return re.sub(r'<[^>]+>', '', html)


def count_words(html):
    """Count Chinese characters + English words from HTML content."""
    text = strip_tags(html).strip()
    if not text:
        return 0
    # Count Chinese characters (CJK unified ideographs)
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', text))
    # Remove Chinese chars, count remaining words by whitespace
    non_chinese = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', ' ', text)
    english_words = len(non_chinese.split())
    return chinese_chars + english_words

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'nl2br'])

MOOD_CHOICES = [
    ('brain', '思考'),
    ('lightbulb', '灵感'),
    ('coffee', '日常'),
    ('book-open', '读书'),
    ('moon', '夜话'),
    ('heart', '开心'),
    ('cloud', '低落'),
    ('graduation-cap', '学习'),
    ('map-pin', '去处'),
    ('film', '观影'),
    ('quote', '感悟'),
    ('pen-line', '随笔'),
]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY') or 'your-deepseek-api-key'
DEEPSEEK_URL = 'https://api.deepseek.com/v1/chat/completions'

def auto_summarize(title, content):
    """Call DeepSeek API to generate summary and tags."""
    if not content or len(content) < 20:
        return None
    prompt = f"""你是一个中文写作助手。请为以下文章生成摘要和标签。

文章标题：{title}
文章内容：{content[:3000]}

请按以下格式回复，不要加其他内容：
摘要：<一句话概括，不超过100字>
标签：<3-5个关键词，用逗号分隔>"""
    data = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': 300
    }).encode('utf-8')
    req = urllib.request.Request(DEEPSEEK_URL, data=data,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        text = result['choices'][0]['message']['content']
        summary, tags = '', ''
        for line in text.strip().split('\n'):
            line = line.strip()
            if line.startswith('摘要：'):
                summary = line[3:].strip()
            elif line.startswith('标签：'):
                tags = line[3:].strip()
        return {'summary': summary, 'tags': tags}
    except Exception as e:
        print(f'[AI Summarize] Error: {e}')
        return None

def render_md(text):
    md.reset()
    return md.convert(text or '')

def render_content(text):
    """Render content that may be HTML (new posts) or Markdown (legacy posts)."""
    if not text:
        return ''
    if re.search(r'<[a-z][\s\S]*?>', text[:200]):
        return text
    return render_md(text)


def compress_image(file, filepath):
    """Compress uploaded image: resize to max 1920px + reduce quality.
    Returns (final_filepath, final_filename) — extension may change to .jpg."""
    import os
    from PIL import Image
    img = Image.open(file)
    img = img.convert('RGB')
    max_dim = 1920
    w, h = img.size
    if w > max_dim or h > max_dim:
        ratio = min(max_dim / w, max_dim / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        img.save(filepath, 'JPEG', quality=85, optimize=True)
        return filepath, os.path.basename(filepath)
    elif ext == '.webp':
        img.save(filepath, 'WEBP', quality=80)
        return filepath, os.path.basename(filepath)
    else:
        filepath_jpg = filepath.rsplit('.', 1)[0] + '.jpg'
        img.save(filepath_jpg, 'JPEG', quality=85, optimize=True)
        if os.path.exists(filepath):
            os.remove(filepath)
        return filepath_jpg, os.path.basename(filepath_jpg)

@app.context_processor
def inject_globals():
    def safe_query(call):
        try:
            return call()
        except Exception:
            return []
    return {
        'site_name': '我的博客',
        'categories': safe_query(get_all_categories),
        'all_tags': safe_query(get_all_tags),
        'recent_footprints': safe_query(lambda: get_all_footprints()[:6]),
        'recent_media_music': safe_query(lambda: get_all_media('music')[:7]),
        'recent_media_anime': safe_query(lambda: get_all_media('anime')[:7]),
        'recent_moments': safe_query(lambda: get_all_moments()[:3]) if session.get('moment_auth') else [],
        'recent_inspirations': safe_query(lambda: get_all_inspirations()[:3]),
        'recent_collections': safe_query(lambda: get_all_collections()[:4]),
        'recent_articles': safe_query(lambda: get_all_articles()[:2]),
        'is_auth': session.get('moment_auth', False),
    }

# --- Routes ---

@app.route('/')
def index():
    keyword = request.args.get('q', '').strip()
    cat_filter = request.args.get('cat', '')

    if keyword:
        articles = search_articles(keyword)
    else:
        articles = get_all_articles()

    if cat_filter:
        articles = [a for a in articles if str(a.get('category_id')) == cat_filter]

    total_count = len(articles)
    show_more = (total_count > 2 and not keyword and not cat_filter)
    if show_more:
        articles = articles[:2]

    # Dashboard stats
    all_arts = get_all_articles()
    total_articles = len(all_arts)
    total_words = sum(len(a.get('content', '')) for a in all_arts)
    from datetime import datetime
    now = datetime.now()
    this_month_articles = [a for a in all_arts if a.get('created_at', '').startswith(now.strftime('%Y-%m'))]
    this_month_count = len(this_month_articles)
    monthly_counts = {}
    for a in all_arts:
        month_key = a.get('created_at', '')[:7]
        if month_key:
            monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
    sorted_months = sorted(monthly_counts.keys(), reverse=True)[:6]

    # Featured articles
    featured = get_featured_articles(6)

    return render_template('index.html', articles=articles, keyword=keyword, show_more=show_more,
        featured=featured,
        stats={'total_articles': total_articles, 'total_words': total_words,
               'this_month': this_month_count, 'monthly_counts': monthly_counts,
               'sorted_months': sorted_months})


@app.route('/articles')
def articles_list():
    """Full article library — all articles, same card style as home."""
    keyword = request.args.get('q', '').strip()
    if keyword:
        articles = search_articles(keyword)
    else:
        articles = get_all_articles()
    return render_template('articles.html', articles=articles, keyword=keyword)


@app.route('/archive')
def archive():
    """Archive page — articles grouped by year/month with word counts."""
    all_articles = get_all_articles()
    # Group by year-month
    from collections import defaultdict
    archive_data = defaultdict(list)
    for a in all_articles:
        ym = a.get('created_at', '')[:7]
        if ym:
            archive_data[ym].append(a)
    sorted_months = sorted(archive_data.keys(), reverse=True)
    # Word count and reading time per article
    for ym in sorted_months:
        for a in archive_data[ym]:
            text = a.get('content', '')
            a['word_count'] = count_words(text)
            a['reading_time'] = max(1, round(a['word_count'] / 300))
    # Totals
    total_articles = len(all_articles)
    total_words = sum(count_words(a.get('content', '')) for a in all_articles)
    return render_template('archive.html',
        archive_data=archive_data, sorted_months=sorted_months,
        total_articles=total_articles, total_words=total_words)


@app.route('/writing')
def writing():
    """Writing hub — top-level category cards + new article button."""
    # Get only top-level categories (parent_id IS NULL)
    all_cats = get_all_categories()
    top_cats = [c for c in all_cats if c.get('parent_id') is None]
    return render_template('writing.html', categories=top_cats)


@app.route('/writing/cat/<int:cat_id>')
def writing_category(cat_id):
    """Articles in a specific category + subcategory cards."""
    category = get_category(cat_id)
    if not category:
        abort(404)
    all_articles = get_all_articles()
    articles = [a for a in all_articles if a.get('category_id') == cat_id]
    subcategories = get_subcategories(cat_id)
    ancestors = get_ancestors(cat_id)
    # Siblings (same level, for quick navigation)
    siblings = get_subcategories(category['parent_id']) if category.get('parent_id') else []
    # Exclude self from siblings
    siblings = [s for s in siblings if s['id'] != cat_id]
    return render_template('articles.html',
        articles=articles, category=category,
        subcategories=subcategories,
        ancestors=ancestors, siblings=siblings)


@app.route('/article/<int:article_id>')
def article_page(article_id):
    article = get_article(article_id)
    if not article:
        abort(404)
    article['content_html'] = render_content(article['content'])

    # Word count + reading time
    text = article.get('content', '')
    # Strip HTML tags for word count
    word_count = count_words(text)
    reading_time = max(1, round(word_count / 300))

    # Previous / Next article by creation time
    all_arts = get_all_articles()
    current_idx = None
    for i, a in enumerate(all_arts):
        if a['id'] == article_id:
            current_idx = i
            break
    prev_article = all_arts[current_idx + 1] if current_idx is not None and current_idx + 1 < len(all_arts) else None
    next_article = all_arts[current_idx - 1] if current_idx is not None and current_idx > 0 else None

    # Related articles (same category)
    related = [a for a in all_arts if a['category_id'] == article['category_id'] and a['id'] != article_id][:4]

    return render_template('article.html', article=article, related=related,
        word_count=word_count, reading_time=reading_time,
        prev_article=prev_article, next_article=next_article)


@app.route('/editor', methods=['GET', 'POST'])
@app.route('/editor/<int:article_id>', methods=['GET', 'POST'])
def editor(article_id=None):
    categories = get_category_tree_flat()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        category_id = request.form.get('category_id', type=int)
        tags = request.form.get('tags', '').strip()
        summary = request.form.get('summary', '').strip()
        cover_image = request.form.get('cover_image', '').strip()

        if not title:
            return '标题不能为空', 400

        featured = 1 if request.form.get('featured') else 0

        if article_id:
            update_article(article_id, title, content, category_id, tags, summary, cover_image, featured)
            return redirect(url_for('article_page', article_id=article_id))
        else:
            aid = create_article(title, content, category_id, tags, summary, cover_image, featured)
            return redirect(url_for('article_page', article_id=aid))

    article = None
    if article_id:
        article = get_article(article_id)
        if not article:
            abort(404)

    return render_template('editor.html', article=article, categories=categories)


@app.route('/delete/<int:article_id>', methods=['POST'])
def delete(article_id):
    delete_article(article_id)
    return redirect(url_for('index'))


@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': '无文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件格式'}), 400

    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    import time
    filename = f"{name}_{int(time.time())}{ext}"

    # Organize by year/month
    from datetime import datetime
    now = datetime.now()
    subdir = os.path.join(str(now.year), f"{now.month:02d}")
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
    os.makedirs(upload_dir, exist_ok=True)

    filepath = os.path.join(upload_dir, filename)

    # Compress image
    try:
        filepath, filename = compress_image(file, filepath)
    except Exception:
        file.seek(0)
        file.save(filepath)

    url = url_for('uploaded_file', filename=f"{subdir}/{filename}")
    return jsonify({'url': url, 'filename': f"{subdir}/{filename}"})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- Admin / Category Management ---

@app.route('/admin')
def admin():
    categories = get_all_categories()
    articles = get_all_articles()
    tags = get_all_tags()
    media_music = get_all_media('music')
    media_anime = get_all_media('anime')
    all_media_items = get_all_media()
    media_types = sorted(set(m['type'] for m in all_media_items))
    collections = get_all_collections()
    all_collection_items = get_all_collections()
    collection_types = sorted(set(c['type'] for c in all_collection_items))
    inspirations = get_all_inspirations()
    all_moments = get_all_moments()
    tree_flat = get_category_tree_flat()
    return render_template('admin.html',
        categories=categories, articles=articles, tags=tags,
        media_music=media_music, media_anime=media_anime,
        all_media_items=all_media_items, media_types=media_types,
        collections=collections, all_collection_items=all_collection_items,
        collection_types=collection_types,
        inspirations=inspirations,
        all_moments=all_moments,
        tree_flat=tree_flat)


@app.route('/admin/category/create', methods=['POST'])
def admin_create_category():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        return '分类名不能为空', 400
    cid = create_category(name, desc)
    if cid is None:
        return '分类名已存在', 400
    return redirect(url_for('admin'))


@app.route('/admin/category/edit/<int:cat_id>', methods=['GET', 'POST'])
def admin_edit_category(cat_id):
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        parent_id = request.form.get('parent_id', type=int) or None
        if not name:
            return '分类名不能为空', 400
        ok = update_category(cat_id, name, desc, parent_id)
        if not ok:
            return '分类名已存在', 400
        return redirect(url_for('admin'))
    cat = get_category(cat_id)
    if not cat:
        abort(404)
    tags = get_all_tags()
    media_music = get_all_media('music')
    media_anime = get_all_media('anime')
    collections = get_all_collections()
    inspirations = get_all_inspirations()
    all_moments = get_all_moments()
    tree_flat = get_category_tree_flat()
    return render_template('admin.html',
        edit_cat=cat, categories=get_all_categories(), articles=get_all_articles(),
        tree_flat=tree_flat,
        tags=tags, media_music=media_music, media_anime=media_anime,
        collections=collections, inspirations=inspirations, all_moments=all_moments)


@app.route('/admin/category/delete/<int:cat_id>', methods=['POST'])
def admin_delete_category(cat_id):
    delete_category(cat_id)
    return redirect(url_for('admin'))


# --- Category Tree API ---

@app.route('/api/category/create', methods=['POST'])
def api_create_category():
    """JSON API for creating a category (from writing page)."""
    data = request.get_json(silent=True) or request.form
    name = data.get('name', '').strip()
    parent_id_raw = data.get('parent_id')
    parent_id = None
    if parent_id_raw:
        try:
            parent_id = int(parent_id_raw)
        except (ValueError, TypeError):
            pass
    if not name:
        return jsonify({'error': '分类名不能为空'}), 400
    cid = create_category(name, '', parent_id)
    if cid is None:
        return jsonify({'error': '分类名已存在'}), 400
    cat = get_category(cid)
    return jsonify({'id': cid, 'name': cat['name'], 'parent_id': cat['parent_id']})


@app.route('/api/article/<int:article_id>/move', methods=['POST'])
def api_move_article(article_id):
    """JSON API for moving article to a different category."""
    data = request.get_json(silent=True) or request.form
    cat_raw = data.get('category_id')
    category_id = None
    if cat_raw:
        try:
            category_id = int(cat_raw)
        except (ValueError, TypeError):
            pass
    move_article_category(article_id, category_id)
    cat_name = ''
    if category_id:
        cat = get_category(category_id)
        if cat:
            cat_name = cat['name']
    return jsonify({'ok': True, 'category_id': category_id, 'category_name': cat_name})


@app.route('/api/categories/tree')
def api_categories_tree():
    """JSON tree of all categories (for editor UI)."""
    tree = get_category_tree_flat()
    result = []
    for c in tree:
        indent = '　' * c['depth'] + ('├ ' if c['depth'] > 0 else '')
        result.append({
            'id': c['id'],
            'name': c['name'],
            'depth': c['depth'],
            'parent_id': c['parent_id'],
            'display': indent + c['name'],
            'article_count': c['article_count']
        })
    return jsonify(result)


# --- Admin: Tags ---


@app.route('/admin/tag/delete/<int:tag_id>', methods=['POST'])
def admin_delete_tag(tag_id):
    delete_tag(tag_id)
    return redirect(url_for('admin'))


@app.route('/admin/tag/edit/<int:tag_id>', methods=['GET', 'POST'])
def admin_edit_tag(tag_id):
    tag = get_tag(tag_id)
    if not tag:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            return '标签名不能为空', 400
        ok = update_tag(tag_id, name)
        if not ok:
            return '标签名已存在', 400
        return redirect(url_for('admin'))
    return render_template('admin_edit.html', entity='标签', item=tag,
        fields=[{'name': 'name', 'label': '标签名', 'value': tag['name']}])


# ════════════════════════════════════════
# Footprints · 时光轴
# ════════════════════════════════════════

@app.route('/footprint')
def footprint():
    footprints = get_all_footprints()
    return render_template('footprint.html', footprints=footprints)


@app.route('/footprint/add', methods=['GET', 'POST'])
def footprint_add():
    if request.method == 'POST':
        # Handle image upload
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                import time
                filename = f"footprint_{int(time.time())}{ext}"
                from datetime import datetime
                now = datetime.now()
                subdir = os.path.join(str(now.year), f"{now.month:02d}")
                upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                try:
                    filepath, filename = compress_image(file, filepath)
                except Exception:
                    file.seek(0)
                    file.save(filepath)
                image_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")
        if not image_url:
            image_url = request.form.get('image_url', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        date = request.form.get('date', '').strip()
        create_footprint(image_url, location, description, date)
        return redirect(url_for('footprint'))
    from datetime import date as dt_date
    return render_template('footprint_add.html', today=dt_date.today().isoformat())


@app.route('/footprint/delete/<int:fid>', methods=['POST'])
def footprint_delete(fid):
    delete_footprint(fid)
    return redirect(url_for('footprint'))


@app.route('/footprint/edit/<int:fid>', methods=['GET', 'POST'])
def footprint_edit(fid):
    fp = get_footprint(fid)
    if not fp:
        abort(404)
    if request.method == 'POST':
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                import time
                filename = f"footprint_{int(time.time())}{ext}"
                from datetime import datetime
                now = datetime.now()
                subdir = os.path.join(str(now.year), f"{now.month:02d}")
                upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                try:
                    filepath, filename = compress_image(file, filepath)
                except Exception:
                    file.seek(0)
                    file.save(filepath)
                image_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")
        if not image_url:
            image_url = request.form.get('image_url', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        date = request.form.get('date', '').strip()
        update_footprint(fid, image_url, location, description, date)
        return redirect(url_for('footprint_detail', fid=fid))
    return render_template('footprint_edit.html', fp=fp)


@app.route('/footprint/<int:fid>')
def footprint_detail(fid):
    fp = get_footprint(fid)
    if not fp:
        abort(404)
    return render_template('footprint_detail.html', fp=fp)


# ════════════════════════════════════════
# Collections · 收藏
# ════════════════════════════════════════

@app.route('/collection')
def collection():
    articles = get_all_collections('article')
    tools = get_all_collections('tool')
    all_collection_items = get_all_collections()
    collection_types = sorted(set(c['type'] for c in all_collection_items))
    return render_template('collection.html', articles=articles, tools=tools,
        all_collection_items=all_collection_items, collection_types=collection_types)


@app.route('/collection/add', methods=['POST'])
def collection_add():
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()
    typ = request.form.get('type', 'article')
    note = request.form.get('note', '').strip()
    if title and url:
        create_collection(title, url, typ, note)
    return redirect(url_for('collection'))


@app.route('/collection/delete/<int:cid>', methods=['POST'])
def collection_delete(cid):
    delete_collection(cid)
    return redirect(url_for('collection'))


@app.route('/collection/edit/<int:cid>', methods=['GET', 'POST'])
def collection_edit(cid):
    all_items = get_all_collections()
    item = next((c for c in all_items if c['id'] == cid), None)
    if not item:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        url = request.form.get('url', '').strip()
        typ = request.form.get('type', '').strip()
        note = request.form.get('note', '').strip()
        if title and url:
            update_collection(cid, title, url, typ, note)
            return redirect(url_for('collection'))
    return render_template('admin_edit.html', entity='收藏', item=item,
        fields=[
            {'name': 'title', 'label': '标题', 'value': item['title']},
            {'name': 'url', 'label': 'URL', 'value': item['url']},
            {'name': 'type', 'label': '分类', 'value': item['type']},
            {'name': 'note', 'label': '备注', 'value': item.get('note', '')},
        ])


# ════════════════════════════════════════
# Auth · 动态密码保护
# ════════════════════════════════════════

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('moment_auth'):
            return redirect(url_for('moment_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/moment/login', methods=['GET', 'POST'])
def moment_login():
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == MOMENT_PASSWORD:
            session['moment_auth'] = True
            session.permanent = True
            app.permanent_session_lifetime = 7 * 24 * 3600  # 7 days
            next_url = request.args.get('next', url_for('moment'))
            return redirect(next_url)
        return render_template('login.html', error='密码错误')
    return render_template('login.html', error=None)

@app.route('/moment/logout')
def moment_logout():
    session.pop('moment_auth', None)
    return redirect(url_for('index'))


# ════════════════════════════════════════
# Moments · 心情动态
# ════════════════════════════════════════

@app.route('/moment')
@login_required
def moment():
    moments = get_all_moments()
    inspirations = get_all_inspirations()
    return render_template('moment.html', moments=moments, inspirations=inspirations, mood_choices=MOOD_CHOICES)


@app.route('/moment/add', methods=['POST'])
@login_required
def moment_add():
    content = request.form.get('content', '').strip()
    image_url = request.form.get('image_url', '').strip()
    mood = request.form.get('mood', '').strip()
    # Handle image upload
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            import time
            filename = f"moment_{int(time.time())}{ext}"
            from datetime import datetime
            now = datetime.now()
            subdir = os.path.join(str(now.year), f"{now.month:02d}")
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            try:
                filepath, filename = compress_image(file, filepath)
            except Exception:
                file.seek(0)
                file.save(filepath)
            image_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")
    if content:
        create_moment(content, image_url, mood)
    return redirect(url_for('moment'))


@app.route('/moment/edit/<int:mid>', methods=['GET', 'POST'])
@login_required
def moment_edit(mid):
    moment_item = get_moment(mid)
    if not moment_item:
        abort(404)
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        image_url = request.form.get('image_url', '').strip()
        mood = request.form.get('mood', '').strip()
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                import time
                filename = f"moment_{int(time.time())}{ext}"
                from datetime import datetime
                now = datetime.now()
                subdir = os.path.join(str(now.year), f"{now.month:02d}")
                upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                try:
                    filepath, filename = compress_image(file, filepath)
                except Exception:
                    file.seek(0)
                    file.save(filepath)
                image_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")
        if content:
            update_moment(mid, content, image_url, mood)
            return redirect(url_for('moment_detail', mid=mid))
    return render_template('moment_edit.html', moment=moment_item, mood_choices=MOOD_CHOICES)


@app.route('/moment/delete/<int:mid>', methods=['POST'])
@login_required
def moment_delete(mid):
    delete_moment(mid)
    return redirect(url_for('moment'))

@app.route('/moment/<int:mid>')
@login_required
def moment_detail(mid):
    moment_item = get_moment(mid)
    if not moment_item:
        abort(404)
    return render_template('item_detail.html', item=moment_item, item_type='moment')


# ════════════════════════════════════════
# Inspirations → 并入动态
# ════════════════════════════════════════

@app.route('/inspiration')
def inspiration():
    return redirect(url_for('moment'))


@app.route('/inspiration/add', methods=['POST'])
def inspiration_add():
    content = request.form.get('content', '').strip()
    tags = request.form.get('tags', '').strip()
    if content:
        create_inspiration(content, tags)
    return redirect(url_for('moment'))


@app.route('/inspiration/delete/<int:iid>', methods=['POST'])
def inspiration_delete(iid):
    delete_inspiration(iid)
    return redirect(url_for('moment'))

@app.route('/inspiration/edit/<int:iid>', methods=['GET', 'POST'])
def inspiration_edit(iid):
    item = get_inspiration(iid)
    if not item:
        abort(404)
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        tags = request.form.get('tags', '').strip()
        if content:
            update_inspiration(iid, content, tags)
            return redirect(url_for('moment'))
    return render_template('admin_edit.html', entity='灵感', item=item,
        fields=[
            {'name': 'content', 'label': '内容', 'value': item['content']},
            {'name': 'tags', 'label': '标签', 'value': item.get('tags', '')},
        ])

@app.route('/inspiration/<int:iid>')
def inspiration_detail(iid):
    inspiration_item = get_inspiration(iid)
    if not inspiration_item:
        abort(404)
    return render_template('item_detail.html', item=inspiration_item, item_type='inspiration')


# ════════════════════════════════════════
# Media · 歌单 & 影视（页面 + API）
# ════════════════════════════════════════

@app.route('/media')
def media_page():
    all_music = get_all_media('music')
    all_anime = get_all_media('anime')
    all_media_items = get_all_media()
    media_types = sorted(set(m['type'] for m in all_media_items))
    return render_template('media.html', all_music=all_music, all_anime=all_anime,
        all_media_items=all_media_items, media_types=media_types)


@app.route('/media/add', methods=['POST'])
def media_add():
    typ = request.form.get('type', 'music')
    title = request.form.get('title', '').strip()
    subtitle = request.form.get('subtitle', '').strip()
    cover_url = request.form.get('cover_url', '').strip()
    link_url = request.form.get('link_url', '').strip()
    status = request.form.get('status', '').strip()
    if not status:
        status = 'watching' if typ == 'anime' else 'watched'
    episode = request.form.get('episode', '')
    sort_order = request.form.get('sort_order', 0, type=int)

    # Handle cover image upload
    if 'cover_file' in request.files:
        file = request.files['cover_file']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            import time
            filename = f"cover_{int(time.time())}{ext}"
            from datetime import datetime
            now = datetime.now()
            subdir = os.path.join(str(now.year), f"{now.month:02d}")
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            try:
                filepath, filename = compress_image(file, filepath)
            except Exception:
                file.seek(0)
                file.save(filepath)
            cover_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")

    if title:
        create_media(typ, title, subtitle, cover_url, link_url, status, episode, sort_order)
    return redirect(url_for('index'))


@app.route('/media/delete/<int:mid>', methods=['POST'])
def media_delete(mid):
    delete_media(mid)
    return redirect(url_for('index'))


@app.route('/media/edit/<int:mid>', methods=['GET', 'POST'])
def media_edit(mid):
    all_items = get_all_media()
    item = next((m for m in all_items if m['id'] == mid), None)
    if not item:
        abort(404)
    if request.method == 'POST':
        typ = request.form.get('type', '').strip()
        title = request.form.get('title', '').strip()
        subtitle = request.form.get('subtitle', '').strip()
        cover_url = request.form.get('cover_url', '').strip()
        link_url = request.form.get('link_url', '').strip()
        status = request.form.get('status', '').strip()
        episode = request.form.get('episode', '').strip()
        sort_order = request.form.get('sort_order', 0, type=int)

        # Handle cover image upload
        if 'cover_file' in request.files:
            file = request.files['cover_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                import time
                filename = f"cover_{int(time.time())}{ext}"
                from datetime import datetime
                now = datetime.now()
                subdir = os.path.join(str(now.year), f"{now.month:02d}")
                upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                try:
                    filepath, filename = compress_image(file, filepath)
                except Exception:
                    file.seek(0)
                    file.save(filepath)
                cover_url = url_for('uploaded_file', filename=f"{subdir}/{filename}")

        if title:
            update_media(mid, typ, title, subtitle, cover_url, link_url, status, episode, sort_order)
            return redirect(url_for('media_page'))
    return render_template('admin_edit.html', entity='条目', item=item,
        fields=[
            {'name': 'type', 'label': '分类', 'value': item['type']},
            {'name': 'title', 'label': '标题', 'value': item['title']},
            {'name': 'subtitle', 'label': '副标题', 'value': item.get('subtitle', '')},
            {'name': 'cover_url', 'label': '封面 URL', 'value': item.get('cover_url', '')},
            {'name': 'link_url', 'label': '链接 URL', 'value': item.get('link_url', '')},
        ])


# ════════════════════════════════════════
# About · 关于我
# ════════════════════════════════════════

@app.route('/about')
def about():
    about_data = {'bio': '', 'contact': '', 'experience': ''}
    about_file = os.path.join(BASE_DIR, 'about_data.json')
    if os.path.exists(about_file):
        with open(about_file, 'r', encoding='utf-8') as f:
            about_data = json.load(f)
    return render_template('about.html', about=about_data)


@app.route('/about/save', methods=['POST'])
def about_save():
    bio = request.form.get('bio', '').strip()
    contact = request.form.get('contact', '').strip()
    experience = request.form.get('experience', '').strip()
    about_file = os.path.join(BASE_DIR, 'about_data.json')
    with open(about_file, 'w', encoding='utf-8') as f:
        json.dump({'bio': bio, 'contact': contact, 'experience': experience}, f, ensure_ascii=False)
    return redirect(url_for('about'))


# ════════════════════════════════════════
# API · 日历
# ════════════════════════════════════════

@app.route('/api/summarize', methods=['POST'])
def api_summarize():
    """AI-generated summary & tags via DeepSeek."""
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    result = auto_summarize(title, content)
    if result:
        return jsonify(result)
    return jsonify({'error': '生成失败，内容太少或 API 异常'}), 400


@app.route('/api/format', methods=['POST'])
def api_format():
    """AI-powered Chinese text formatting — paragraph indent, spacing, punctuation."""
    content = request.form.get('content', '').strip()
    if not content or len(content) < 10:
        return jsonify({'error': '内容太少'}), 400
    prompt = f"""你是一个中文排版助手。请对以下 HTML 内容进行文字层面的排版优化，不修改任何样式属性：

排版规则（按优先级）：
1. 中英文之间加一个空格（如"Python语言"→"Python 语言"）
2. 中文数字之间加一个空格（如"第1章"→"第 1 章"）
3. 中文标点统一为全角（，。！？；：“”【】《》）
4. 英文标点保持半角
5. 多余的空行和 <br> 合并为单个
6. 清除 mso- 相关的内联样式污染
7. 保持所有 HTML 标签和现有样式属性不变（不添加、不删除任何 style 属性）
8. **根据文章类型决定段落间距**：如果内容偏向技术/代码类（包含较多代码、技术术语、配置等），段落间保持紧凑，不加空行分隔；如果内容偏向叙事/散文类（文学性、个人随笔、游记等），每个自然段之间加一个 `</p><p><br></p>` 空行分隔，确保段落间有视觉间距，不拥挤
9. **代码块标注**：如果内容中包含 `<pre>` 代码块或反引号代码段，检测编程语言并在 `<code>` 标签上加 `class="language-xxx"`（如 `class="language-python"`、`class="language-javascript"`、`class="language-css"`、`class="language-html"`、`class="language-bash"` 等）。如果无法确定语言，用 `class="language-plaintext"`
10. **引用标注**：如果内容中包含引文（格式如「xxx说："..."」或明显的引用段落），用 `<blockquote class="pullquote">` 包裹。引文来源标注（如「——xxx」）放在 `<cite>` 标签内

要处理的 HTML：
{content[:30000]}

注意：如果文章较长，请逐段处理所有段落，不要遗漏任何内容。"""
    data = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 16384
    }).encode('utf-8')
    req = urllib.request.Request(DEEPSEEK_URL, data=data,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {DEEPSEEK_API_KEY}'})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        text = result['choices'][0]['message']['content'].strip()
        # Extract HTML from markdown code fences if present
        if text.startswith('```'):
            text = re.sub(r'^```(html)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        # If there's explanatory text outside HTML, strip it:
        # find first '<' and last '>' to extract the actual HTML
        first_lt = text.find('<')
        last_gt = text.rfind('>')
        if first_lt != -1 and last_gt != -1 and first_lt < last_gt:
            text = text[first_lt:last_gt+1]
        if not text.startswith('<'):
            return jsonify({'error': 'AI 返回格式异常，请重试'}), 500
        return jsonify({'content': text})
    except Exception as e:
        print(f'[AI Format] Error: {e}')
        return jsonify({'error': '排版请求失败，请稍后重试'}), 500


@app.route('/api/calendar')
def api_calendar():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    from datetime import datetime
    now = datetime.now()
    if not year: year = now.year
    if not month: month = now.month
    counts = get_article_counts_by_month(year, month)
    return jsonify({'year': year, 'month': month, 'counts': counts})


# ════════════════════════════════════════
# Tags · 标签聚合页
# ════════════════════════════════════════

@app.route('/tag/<tag_name>')
def tag_page(tag_name):
    tag = get_tag(tag_name)
    if not tag:
        abort(404)
    articles = get_articles_by_tag(tag['id'])
    return render_template('index.html', articles=articles, keyword=f'标签: {tag_name}')


@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error_404=True), 404


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8765, debug=False)
