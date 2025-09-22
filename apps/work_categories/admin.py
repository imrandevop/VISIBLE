# apps/work_categories/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponseRedirect
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection,
    UserWorkSubCategory, WorkPortfolioImage, ServiceRequest
)
from apps.work_categories.forms import BulkSubCategoryForm


class WorkSubCategoryInline(admin.TabularInline):
    model = WorkSubCategory
    extra = 1
    fields = ['subcategory_code', 'name', 'display_name', 'description', 'is_active', 'sort_order']
    readonly_fields = ['subcategory_code']


@admin.register(WorkCategory)
class WorkCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'category_code',
        'display_name',
        'name',
        'subcategory_count',
        'active_users_count',
        'is_active',
        'sort_order',
        'created_at'
    ]
    
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    ordering = ['sort_order', 'name']
    
    fieldsets = (
        (None, {
            'fields': (
                'category_code',
                'name',
                'display_name',
                'description',
                'is_active',
                'sort_order'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['category_code', 'created_at', 'updated_at']
    inlines = [WorkSubCategoryInline]
    
    def subcategory_count(self, obj):
        count = obj.subcategories.count()
        url = f"/admin/work_categories/worksubcategory/?category__id__exact={obj.id}"
        return format_html('<a href="{}">{} subcategories</a>', url, count)
    subcategory_count.short_description = 'Subcategories'
    
    def active_users_count(self, obj):
        count = UserWorkSelection.objects.filter(main_category=obj).count()
        return f"{count} users"
    active_users_count.short_description = 'Users Count'


@admin.register(WorkSubCategory)
class WorkSubCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'subcategory_code',
        'display_name',
        'name',
        'category',
        'users_count',
        'is_active',
        'sort_order'
    ]

    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    ordering = ['subcategory_code']

    fieldsets = (
        (None, {
            'fields': (
                'subcategory_code',
                'category',
                'name',
                'display_name',
                'description',
                'is_active',
                'sort_order'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ['subcategory_code', 'created_at', 'updated_at']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-create/', self.bulk_create_view, name='worksubcategory_bulk_create'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['bulk_create_url'] = reverse('admin:worksubcategory_bulk_create')
        return super().changelist_view(request, extra_context)

    def bulk_create_view(self, request):
        if request.method == 'POST':
            form = BulkSubCategoryForm(request.POST)
            if form.is_valid():
                category = form.cleaned_data['category']
                names = form.cleaned_data['subcategory_names'].strip().split('\n')
                names = [name.strip() for name in names if name.strip()]

                created_count = 0
                skipped_count = 0

                # Get the last sort order for this category
                last_subcategory = WorkSubCategory.objects.filter(category=category).order_by('-sort_order').first()
                next_sort_order = (last_subcategory.sort_order + 1) if last_subcategory else 1

                for name in names:
                    # Check if subcategory already exists for this category
                    if not WorkSubCategory.objects.filter(category=category, name=name).exists():
                        WorkSubCategory.objects.create(
                            category=category,
                            name=name,
                            display_name=name,
                            description='',
                            is_active=True,
                            sort_order=next_sort_order
                        )
                        created_count += 1
                        next_sort_order += 1
                    else:
                        skipped_count += 1

                if created_count > 0:
                    messages.success(request, f'Successfully created {created_count} subcategories.')
                if skipped_count > 0:
                    messages.warning(request, f'Skipped {skipped_count} subcategories (already exist).')

                return HttpResponseRedirect(reverse('admin:work_categories_worksubcategory_changelist'))
        else:
            form = BulkSubCategoryForm()

        context = {
            'form': form,
            'title': 'Bulk Create Subcategories',
            'opts': self.model._meta,
            'has_change_permission': self.has_change_permission(request),
        }
        return render(request, 'admin/work_categories/bulk_create_subcategories.html', context)

    def users_count(self, obj):
        count = UserWorkSubCategory.objects.filter(sub_category=obj).count()
        return f"{count} users"
    users_count.short_description = 'Users Count'


class UserWorkSubCategoryInline(admin.TabularInline):
    model = UserWorkSubCategory
    extra = 0
    readonly_fields = ['created_at']


class WorkPortfolioImageInline(admin.TabularInline):
    model = WorkPortfolioImage
    extra = 0
    readonly_fields = ['image_preview', 'created_at']
    fields = ['image', 'image_preview', 'image_order', 'created_at']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 80px; height: 80px; object-fit: cover;" />',
                obj.image.url
            )
        return "No Image"
    image_preview.short_description = 'Preview'


@admin.register(UserWorkSelection)
class UserWorkSelectionAdmin(admin.ModelAdmin):
    list_display = [
        'user_profile_name',
        'mobile_number', 
        'main_category', 
        'years_experience',
        'subcategories_list',
        'portfolio_count',
        'created_at'
    ]
    
    list_filter = [
        'main_category', 
        'years_experience',
        'created_at'
    ]
    
    search_fields = [
        'user__full_name',
        'user__user__mobile_number',
        'skills_description'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': (
                'user',
                'user_profile_link'
            )
        }),
        ('Work Details', {
            'fields': (
                'main_category',
                'years_experience', 
                'skills_description'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = [
        'created_at', 
        'updated_at',
        'user_profile_link'
    ]
    
    inlines = [UserWorkSubCategoryInline, WorkPortfolioImageInline]
    
    def user_profile_name(self, obj):
        return obj.user.full_name
    user_profile_name.short_description = 'User Name'
    user_profile_name.admin_order_field = 'user__full_name'
    
    def mobile_number(self, obj):
        return obj.user.user.mobile_number
    mobile_number.short_description = 'Mobile'
    mobile_number.admin_order_field = 'user__user__mobile_number'
    
    def subcategories_list(self, obj):
        subcats = obj.selected_subcategories.all()
        if subcats:
            names = [sub.sub_category.display_name for sub in subcats]
            return ", ".join(names)
        return "None"
    subcategories_list.short_description = 'Subcategories'
    
    def portfolio_count(self, obj):
        count = obj.portfolio_images.count()
        return f"{count} images"
    portfolio_count.short_description = 'Portfolio'
    
    def user_profile_link(self, obj):
        url = reverse('admin:profiles_userprofile_change', args=[obj.user.id])
        return format_html('<a href="{}" target="_blank">View Profile</a>', url)
    user_profile_link.short_description = 'User Profile'


@admin.register(WorkPortfolioImage)
class WorkPortfolioImageAdmin(admin.ModelAdmin):
    list_display = [
        'user_name',
        'mobile_number',
        'work_category',
        'image_preview',
        'image_order',
        'created_at'
    ]
    
    list_filter = [
        'user_work_selection__main_category',
        'image_order',
        'created_at'
    ]
    
    search_fields = [
        'user_work_selection__user__full_name',
        'user_work_selection__user__user__mobile_number'
    ]
    
    readonly_fields = ['created_at', 'image_preview']
    
    def user_name(self, obj):
        return obj.user_work_selection.user.full_name
    user_name.short_description = 'User Name'
    
    def mobile_number(self, obj):
        return obj.user_work_selection.user.user.mobile_number
    mobile_number.short_description = 'Mobile'
    
    def work_category(self, obj):
        return obj.user_work_selection.main_category.display_name
    work_category.short_description = 'Category'
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 100px; height: 100px; object-fit: cover;" />',
                obj.image.url
            )
        return "No Image"
    image_preview.short_description = 'Preview'


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = [
        'user_mobile',
        'service_name_preview',
        'created_at'
    ]

    list_filter = ['created_at']
    search_fields = ['user__mobile_number', 'service_name']
    ordering = ['-created_at']

    fieldsets = (
        ('Request Information', {
            'fields': (
                'user',
                'service_name'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ['created_at', 'updated_at']

    def user_mobile(self, obj):
        return obj.user.mobile_number
    user_mobile.short_description = 'Mobile Number'
    user_mobile.admin_order_field = 'user__mobile_number'

    def service_name_preview(self, obj):
        if len(obj.service_name) > 50:
            return obj.service_name[:50] + "..."
        return obj.service_name
    service_name_preview.short_description = 'Service Name'
    service_name_preview.admin_order_field = 'service_name'