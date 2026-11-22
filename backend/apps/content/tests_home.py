"""The public home page follows the design mock-up: same sections, working links only, three languages, real news from the database."""
import re

from django.test import TestCase
from django.urls import reverse

from .tests import news

SECTIONS = ("yangiliklar", "yutuqlar", "media", "hujjatlar", "boglanish")


class HomePageTests(TestCase):
    def get(self, lang="uz"):
        return self.client.get(reverse("content:home"), HTTP_COOKIE=f"django_language={lang}")

    def test_all_mockup_sections_are_present_with_anchors_the_menu_points_to(self):
        body = self.get().content.decode()
        for anchor in SECTIONS:
            self.assertIn(f'id="{anchor}"', body, anchor)
        for anchor in ("yutuqlar", "hujjatlar"):
            self.assertIn(f"#{anchor}", body)
        self.assertIn('href="/media/"', body)  # the menu's Media is the real gallery page now (the "media" section stays on the home page)
        for marker in ('class="hero"', 'class="stats"', 'class="gallery"', 'class="video"', 'class="teachers"', 'class="map-card"'):
            self.assertIn(marker, body, marker)

    def test_there_are_no_links_to_pages_that_do_not_exist_yet(self):
        body = self.get().content.decode()
        self.assertEqual(re.findall(r'href="[^"#?][^"]*\.html', body), [])
        for href in re.findall(r'href="(/[^"#?]*)"', body):
            if href.startswith("/static/") or href.startswith("/set-language"):
                continue
            self.assertIn(self.client.get(href).status_code, (200, 302), href)

    def test_sample_blocks_are_marked_as_mock_up_not_presented_as_real(self):
        body = self.get().content.decode()
        self.assertGreaterEqual(body.count('class="demo-tag"'), 3)
        self.assertIn("namunaviy ma’lumot", body)

    def test_real_news_replace_the_empty_state_and_at_most_three_are_shown_in_the_grid(self):
        self.assertContains(self.get(), "Hozircha yangiliklar yo‘q")
        for index in range(5):
            news(f"Yangilik raqami {index}", slug=f"yangilik-{index}")
        body = self.get().content.decode()
        self.assertNotIn("Hozircha yangiliklar yo‘q", body)
        self.assertEqual(body.count('class="card news-card"'), 3)

    def test_the_page_is_translated_into_russian_and_english(self):
        ru = self.get("ru").content.decode()
        for text in ("Достижения учителей", "Образец: учитель", "Фотогалерея", "Важные ссылки", "Объявления"):
            self.assertIn(text, ru)
        en = self.get("en").content.decode()
        for text in ("Teachers' achievements", "Sample Teacher", "Photo gallery", "Important links", "Announcements"):
            self.assertIn(text, en)
        self.assertNotIn("Fotorasmlar", ru + en)
