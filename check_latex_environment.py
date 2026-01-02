#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX环境检查脚本
检查系统是否安装了LaTeX编译器，并提供安装指导
"""

import subprocess
import sys
import os
import platform

def check_latex_installation():
    """检查LaTeX是否已安装"""
    print("=" * 60)
    print("LaTeX环境检查工具")
    print("=" * 60)
    
    # 检查XeLaTeX
    try:
        result = subprocess.run(['xelatex', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ XeLaTeX 已安装")
            version_line = result.stdout.split('\n')[0]
            print(f"版本信息：{version_line}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ XeLaTeX 未安装")
    
    # 检查pdflatex
    try:
        result = subprocess.run(['pdflatex', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ PDFLaTeX 已安装")
            version_line = result.stdout.split('\n')[0]
            print(f"版本信息：{version_line}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ PDFLaTeX 未安装")
    
    return False

def provide_installation_guide():
    """提供LaTeX安装指导"""
    system = platform.system().lower()
    
    print("\\n" + "=" * 60)
    print("LaTeX安装指导")
    print("=" * 60)
    
    if system == "windows":
        print("Windows系统安装选项：")
        print("1. MiKTeX (推荐)")
        print("   - 下载地址：https://miktex.org/download")
        print("   - 选择完整安装包")
        print("   - 安装后重启命令行")
        print()
        print("2. TeX Live")
        print("   - 下载地址：https://www.tug.org/texlive/")
        print("   - 选择Windows版本")
        print("   - 安装时间较长，但功能完整")
        
    elif system == "darwin":  # macOS
        print("macOS系统安装选项：")
        print("1. MacTeX (推荐)")
        print("   - 下载地址：https://www.tug.org/mactex/")
        print("   - 完整安装包，包含所有组件")
        print()
        print("2. 使用Homebrew")
        print("   - 运行：brew install --cask mactex")
        
    elif system == "linux":
        print("Linux系统安装选项：")
        print("1. Ubuntu/Debian:")
        print("   sudo apt-get install texlive-full")
        print()
        print("2. CentOS/RHEL:")
        print("   sudo yum install texlive")
        print()
        print("3. Arch Linux:")
        print("   sudo pacman -S texlive-most")
    
    print("\\n" + "=" * 60)
    print("安装完成后，请重新运行此脚本检查")

def create_simple_html_presentation():
    """创建简单的HTML演示文稿作为替代方案"""
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能教育成绩分析系统</title>
    <style>
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .slide {
            background: white;
            margin: 20px 0;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            page-break-after: always;
        }
        .slide h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        .slide h2 {
            color: #34495e;
            margin-top: 30px;
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .feature-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }
        .feature-card h3 {
            color: #2c3e50;
            margin-top: 0;
        }
        .highlight {
            background: #e8f5e8;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #27ae60;
            margin: 15px 0;
        }
        .stats {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            margin: 20px 0;
        }
        .stat-item {
            text-align: center;
            background: #ecf0f1;
            padding: 20px;
            border-radius: 10px;
            margin: 10px;
            flex: 1;
            min-width: 200px;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #27ae60;
        }
        @media print {
            .slide {
                page-break-after: always;
                margin: 0;
                box-shadow: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="slide">
            <h1>智能教育成绩分析系统</h1>
            <h2>教育信息化新突破</h2>
            <div class="highlight">
                <p><strong>基于大数据与人工智能技术构建的现代化教育管理平台</strong></p>
                <p>通过科学的数据分析，为教育决策提供精准支撑</p>
            </div>
        </div>

        <div class="slide">
            <h1>核心价值</h1>
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>让教育决策更科学</h3>
                    <ul>
                        <li>用数据说话，告别经验决策</li>
                        <li>实时监控教育质量变化</li>
                        <li>精准识别问题，及时调整策略</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>让教学质量更精准</h3>
                    <ul>
                        <li>客观评价教学效果</li>
                        <li>个性化学生指导</li>
                        <li>因材施教，提升效率</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>让教育管理更高效</h3>
                    <ul>
                        <li>自动化数据分析</li>
                        <li>可视化结果展示</li>
                        <li>大幅减少人工统计工作</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="slide">
            <h1>主要功能</h1>
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>智能成绩分析</h3>
                    <ul>
                        <li>T分数标准化</li>
                        <li>多维度统计</li>
                        <li>趋势预测</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>增值评估体系</h3>
                    <ul>
                        <li>教学质量增值</li>
                        <li>学生成长跟踪</li>
                        <li>学校发展评估</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>发展跟踪分析</h3>
                    <ul>
                        <li>学生画像</li>
                        <li>群体分析</li>
                        <li>个性化指导</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>区域特征分析</h3>
                    <ul>
                        <li>教育均衡监测</li>
                        <li>资源配置优化</li>
                        <li>政策效果评估</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="slide">
            <h1>核心优势</h1>
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>科学化评估</h3>
                    <ul>
                        <li>建立标准化评估体系</li>
                        <li>消除主观因素影响</li>
                        <li>提供客观评价依据</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>智能化分析</h3>
                    <ul>
                        <li>自动发现教育规律</li>
                        <li>智能识别问题</li>
                        <li>提供改进建议</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>可视化展示</h3>
                    <ul>
                        <li>丰富的图表展示</li>
                        <li>直观的结果呈现</li>
                        <li>移动端适配</li>
                    </ul>
                </div>
                <div class="feature-card">
                    <h3>开放兼容</h3>
                    <ul>
                        <li>标准API接口</li>
                        <li>支持系统集成</li>
                        <li>多机构使用</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="slide">
            <h1>应用效果</h1>
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-number">80%</div>
                    <div>分析效率提升</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">60%</div>
                    <div>决策准确性提升</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">70%</div>
                    <div>管理成本降低</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">15%</div>
                    <div>教学质量提升</div>
                </div>
            </div>
            <div class="highlight">
                <h3>管理价值</h3>
                <ul>
                    <li><strong>科学决策</strong>：数据驱动，告别拍脑袋决策</li>
                    <li><strong>精准管理</strong>：精准识别问题，精准施策</li>
                    <li><strong>过程监控</strong>：实时监控，及时调整</li>
                    <li><strong>持续改进</strong>：建立质量保障长效机制</li>
                </ul>
            </div>
        </div>

        <div class="slide">
            <h1>总结</h1>
            <div class="highlight">
                <h2>让数据驱动教育，让科技赋能未来！</h2>
                <p>智能教育成绩分析系统致力于为教育现代化提供技术支撑，助力教育质量全面提升。</p>
            </div>
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>教育决策科学化</h3>
                    <p>从经验决策转向数据驱动决策</p>
                </div>
                <div class="feature-card">
                    <h3>教学质量精准化</h3>
                    <p>个性化教育，因材施教</p>
                </div>
                <div class="feature-card">
                    <h3>教育管理现代化</h3>
                    <p>全流程数字化管理</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''
    
    with open('智能教育成绩分析系统演示文稿.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("\\n✅ 已创建HTML演示文稿：智能教育成绩分析系统演示文稿.html")
    print("可以在浏览器中打开查看，支持打印为PDF")

def main():
    """主函数"""
    if check_latex_installation():
        print("\\n✅ LaTeX环境检查通过！")
        print("\\n可以运行以下命令编译演示文稿：")
        print("1. 双击 compile_presentation.bat")
        print("2. 或在命令行运行：xelatex 智能教育成绩分析系统演示文稿.tex")
    else:
        print("\\n❌ LaTeX环境未安装")
        provide_installation_guide()
        
        # 创建HTML替代方案
        print("\\n" + "=" * 60)
        print("创建HTML演示文稿作为替代方案...")
        create_simple_html_presentation()
        
        print("\\n" + "=" * 60)
        print("使用建议：")
        print("1. 安装LaTeX后编译.tex文件获得最佳效果")
        print("2. 或直接使用HTML文件在浏览器中展示")
        print("3. HTML文件支持打印为PDF格式")

if __name__ == "__main__":
    main()