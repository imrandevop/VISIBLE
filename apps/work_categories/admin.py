# apps/work_categories/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection, 
    UserWorkSubCategory, WorkPortfolioImage
)


class WorkSubCategoryInline(admin.TabularInline):
    model = WorkSubCategory
    extra = 1
    fields = ['name', 'display_name', 'description', 'is_active', 'sort_order']


@admin.register(WorkCategory)
class WorkCategoryAdmin(admin.ModelAdmin):
    list_display = [
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
    
    readonly_fields = ['created_at', 'updated_at']
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
        'display_name', 
        'name', 
        'category', 
        'users_count',
        'is_active', 
        'sort_order'
    ]
    
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    ordering = ['category__sort_order', 'sort_order', 'name']
    
    fieldsets = (
        (None, {
            'fields': (
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
    
    readonly_fields = ['created_at', 'updated_at']
    
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