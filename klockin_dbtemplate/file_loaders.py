"""Load renamed filesystem templates included by database-authored templates."""

from django.template.loaders import app_directories, filesystem

from .paths import template_names


class FilesystemLoader(filesystem.Loader):
    def get_template_sources(self, template_name):
        return super().get_template_sources(template_names(template_name)[0])


class AppDirectoriesLoader(app_directories.Loader):
    def get_template_sources(self, template_name):
        return super().get_template_sources(template_names(template_name)[0])
