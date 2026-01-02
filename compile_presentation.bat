@echo off
echo 正在编译LaTeX演示文稿...

REM 检查是否安装了LaTeX
where xelatex >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误：未找到XeLaTeX编译器
    echo 请安装TeX Live或MiKTeX
    pause
    exit /b 1
)

REM 编译LaTeX文件
echo 第一次编译...
xelatex -interaction=nonstopmode "智能教育成绩分析系统演示文稿.tex"

echo 第二次编译...
xelatex -interaction=nonstopmode "智能教育成绩分析系统演示文稿.tex"

REM 清理临时文件
echo 清理临时文件...
del *.aux *.log *.nav *.out *.snm *.toc *.vrb 2>nul

echo 编译完成！
echo 生成的PDF文件：智能教育成绩分析系统演示文稿.pdf
pause