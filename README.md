# 个人博客系统

一个基于 Flask 的个人博客应用，支持文章管理、分类整理、足迹记录、收藏管理、心情动态、歌单影视管理等功能。

## 功能特性

- **写作** - 富文本编辑器（Quill），支持分类、标签、封面图、AI 摘要
- **分类卡片** - 树形分类结构，支持无限层级子分类
- **归档** - 按月归档，字数统计，阅读时间估算
- **足迹** - 照片+地点+描述的时光轴
- **收藏** - 链接收藏管理
- **动态** - 密码保护的心情记录，支持心情标签和配图
- **歌单与影视** - 音乐/影视条目管理
- **深色模式** - 自适应系统主题，支持手动切换
- **日历热力图** - 首页展示写作活跃度
- **搜索** - 文章全文搜索

## 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd blog

# 安装依赖
pip install -r requirements.txt

# 运行
python app.py
```

默认启动在 `http://localhost:5000`

### 环境变量配置（可选）

```bash
# Flask 密钥（必改！用于 session 加密）
export BLOG_SECRET_KEY="your-random-secret-key"

# 动态模块访问密码
export BLOG_MOMENT_PASSWORD="your-password"

# DeepSeek API Key（AI 摘要与排版功能）
export DEEPSEEK_API_KEY="your-api-key"
```

不设置环境变量时，会使用代码中的默认值（仅用于开发测试）。

## 技术栈

- **后端**: Flask, SQLite
- **前端**: Quill.js (富文本编辑器), Lucide (图标), Highlight.js (代码高亮)
- **AI**: DeepSeek API (自动摘要、排版)

## 项目结构

```
blog/
├── app.py              # 主应用 + 路由
├── models.py           # 数据库模型
├── requirements.txt    # Python 依赖
├── static/
│   ├── style.css       # 全局样式
│   └── favicon.svg     # 网站图标
├── templates/          # Jinja2 模板
│   ├── base.html       # 基础模板
│   ├── index.html      # 首页
│   ├── article.html    # 文章详情
│   ├── editor.html     # 编辑器
│   ├── admin.html      # 管理后台
│   └── ...             # 其他页面
└── uploads/            # 上传文件（自动创建）
```

## License

MIT
