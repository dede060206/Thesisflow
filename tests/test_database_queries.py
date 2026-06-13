from app.database import eligible_article_sql


def test_eligible_article_sql_aliases_columns_without_changing_parameters():
    sql = eligible_article_sql("a")

    assert "a.page_type" in sql
    assert "a.quality_score" in sql
    assert "a.published_at" in sql
    assert "%(quality_score_threshold)s" in sql
    assert "%(min_article_date)s" in sql
    assert "%(a.quality_score_threshold)s" not in sql
    assert "%(min_a.article_date)s" not in sql
