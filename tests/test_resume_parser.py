"""
简历解析器功能测试脚本

测试 ResumeParser 类的各项功能，包括：
- 文件验证
- 格式检测
- TXT文件解析
- 错误处理
"""

import sys
import os
import io

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置控制台输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.resume_parser import ResumeParser


def test_validation():
    """测试文件验证功能"""
    print("\n【测试1】文件验证功能")
    print("-" * 50)

    parser = ResumeParser()

    # 测试不存在的文件
    result = parser._validate_file("不存在的文件.pdf")
    assert result['valid'] == False, "不存在文件应该验证失败"
    assert '不存在' in result['error'], "错误信息应包含'不存在'"
    print(f"✓ 不存在的文件: 验证通过")

    # 测试目录路径（应该失败）
    test_dir = os.path.dirname(os.path.abspath(__file__))
    result = parser._validate_file(test_dir)
    assert result['valid'] == False, "目录路径应该验证失败"
    print(f"✓ 目录路径: 验证通过")


def test_format_detection():
    """测试格式检测功能"""
    print("\n【测试2】文件格式检测")
    print("-" * 50)

    parser = ResumeParser()

    # 测试各种扩展名
    test_cases = [
        ("resume.pdf", ".pdf", True),
        ("document.docx", ".docx", True),
        ("old.doc", ".doc", True),
        ("note.txt", ".txt", True),
        ("photo.png", ".png", True),
        ("image.jpg", ".jpg", True),
        ("picture.jpeg", ".jpeg", True),
        ("data.xlsx", ".xlsx", False),  # 不支持的格式
        ("archive.zip", ".zip", False),  # 不支持的格式
    ]

    for filename, expected_ext, expected_supported in test_cases:
        detected = parser._detect_format(filename)
        supported = parser._is_supported_format(detected)

        assert detected == expected_ext, f"{filename}: 扩展名检测错误，期望 {expected_ext}，实际 {detected}"
        assert supported == expected_supported, f"{filename}: 支持状态错误"

        status = "✓ 支持" if supported else "✗ 不支持"
        print(f"  {filename:20s} → {detected:6s} [{status}]")

    print("✓ 所有格式检测通过")


def test_txt_parsing():
    """测试TXT文件解析"""
    print("\n【测试3】TXT文件解析测试")
    print("-" * 50)

    parser = ResumeParser()

    # 创建测试用的TXT文件
    test_content = """张三
Python开发工程师

教育背景：
- 本科 · 计算机科学与技术 · XX大学 · 2015-2019

工作经验：
1. ABC科技有限公司 · Python开发工程师 · 2019-2022
   - 负责后端API开发和数据库设计

技能特长：
- Python, Django, MySQL
"""

    test_file_path = os.path.join(os.path.dirname(__file__), "test_resume.txt")

    try:
        # 写入UTF-8编码的测试文件
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write(test_content)
        print(f"✓ 创建测试文件: {test_file_path}")

        # 解析文件
        result = parser.parse_resume_file(test_file_path)

        # 验证结果
        assert result['success'] == True, "解析应该成功"
        assert result['file_type'] == 'text', "类型应该是text"
        assert isinstance(result['content'], str), "内容应该是字符串"
        assert len(result['content']) > 0, "内容不应为空"
        assert result['error'] is None, "不应该有错误"
        assert result['metadata']['filename'] == 'test_resume.txt', "文件名应正确"
        assert result['metadata']['format'] == '.txt', "格式应正确"
        assert result['metadata']['size'] > 0, "大小应大于0"

        print(f"\n✓ 解析结果验证:")
        print(f"  成功: {result['success']}")
        print(f"  类型: {result['file_type']}")
        print(f"  内容长度: {len(result['content'])} 字符")
        print(f"  文件大小: {result['metadata']['size']} 字节")
        print(f"\n--- 内容预览 ---")
        preview = result['content'][:150] + "..." if len(result['content']) > 150 else result['content']
        print(preview)

    finally:
        # 清理测试文件
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
            print(f"\n✓ 已清理测试文件")


def test_error_handling():
    """测试错误处理"""
    print("\n【测试4】错误处理测试")
    print("-" * 50)

    parser = ResumeParser()

    # 测试1：文件不存在
    print("\n测试4.1: 文件不存在")
    result = parser.parse_resume_file("绝对不存在的文件_12345.pdf")
    assert result['success'] == False, "应该返回失败"
    assert '不存在' in result['error'], "错误信息应包含'不存在'"
    print(f"✓ 返回错误: {result['error']}")

    # 测试2：不支持的格式
    print("\n测试4.2: 不支持的文件格式")
    unsupported_file = os.path.join(os.path.dirname(__file__), "test_unsupported.xyz")
    try:
        with open(unsupported_file, 'w') as f:
            f.write("test content")

        result = parser.parse_resume_file(unsupported_file)
        assert result['success'] == False, "应该返回失败"
        assert '不支持' in result['error'], "错误信息应包含'不支持'"
        print(f"✓ 返回错误: {result['error']}")
    finally:
        if os.path.exists(unsupported_file):
            os.remove(unsupported_file)

    # 测试3：空文件
    print("\n测试4.3: 空文件")
    empty_file = os.path.join(os.path.dirname(__file__), "test_empty.txt")
    try:
        with open(empty_file, 'w') as f:
            pass  # 创建空文件

        result = parser.parse_resume_file(empty_file)
        assert result['success'] == False, "空文件应该返回失败"
        assert '空' in result['error'], "错误信息应包含'空'"
        print(f"✓ 返回错误: {result['error']}")
    finally:
        if os.path.exists(empty_file):
            os.remove(empty_file)


def test_encoding_detection():
    """测试不同编码的TXT文件"""
    print("\n【测试5】多编码支持测试")
    print("-" * 50)

    parser = ResumeParser()

    test_text = "这是中文测试内容\nEnglish content here\n混合内容 Mixed"

    encodings_to_test = [
        ('utf-8', 'UTF-8'),
        ('gbk', 'GBK'),
        ('gb2312', 'GB2312'),
    ]

    for encoding, label in encodings_to_test:
        test_file = os.path.join(os.path.dirname(__file__), f"test_{encoding}.txt")
        try:
            with open(test_file, 'w', encoding=encoding) as f:
                f.write(test_text)

            result = parser.parse_resume_file(test_file)
            assert result['success'] == True, f"{label} 编码解析应该成功"
            assert test_text.split('\n')[0] in result['content'], "应包含原始文本"
            print(f"✓ {label:6s} 编码: 解析成功 ({len(result['content'])}字符)")
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


def test_metadata():
    """测试元数据构建"""
    print("\n【测试6】元数据构建测试")
    print("-" * 50)

    parser = ResumeParser()

    # 测试存在的文件
    test_file = __file__
    metadata = parser._build_metadata(test_file)

    assert 'filename' in metadata, "应包含filename字段"
    assert 'size' in metadata, "应包含size字段"
    assert 'format' in metadata, "应包含format字段"
    assert metadata['size'] > 0, "大小应大于0"
    assert metadata['format'] == '.py', "格式应为.py"

    print(f"✓ 元数据构建正确:")
    for key, value in metadata.items():
        print(f"  {key}: {value}")

    # 测试不存在的文件
    metadata_empty = parser._build_metadata("不存在的文件.txt")
    assert metadata_empty['size'] == 0, "不存在文件大小应为0"
    print(f"✓ 不存在文件的元数据处理正确")


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("简历文件预处理解析器 - 完整功能测试")
    print("=" * 70)

    try:
        test_validation()
        test_format_detection()
        test_txt_parsing()
        test_error_handling()
        test_encoding_detection()
        test_metadata()

        print("\n" + "=" * 70)
        print("[SUCCESS] ✓ 所有测试用例通过！")
        print("=" * 70)
        return True

    except AssertionError as e:
        print("\n" + "=" * 70)
        print(f"[FAILED] ✗ 测试失败: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"[ERROR] ✗ 测试异常: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
