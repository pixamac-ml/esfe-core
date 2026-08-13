from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0027_remove_academiccalendarentry_supervisors"),
        ("students", "0013_alter_studentcase_status_teachercase_convocation_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="attendancerollsheet",
            name="students_unique_roll_sheet_branch_class_date",
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="is_justified",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Indique si l'absence a ete justifiee par un motif recevable.",
            ),
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="observation",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="teacherattendance",
            name="course_delivered",
            field=models.BooleanField(
                blank=True,
                db_index=True,
                help_text="Constat du surveillant : le cours programme a-t-il ete assure ?",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="teacherattendance",
            name="observation",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="studentcase",
            name="academic_class",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="student_signalments",
                to="academics.academicclass",
            ),
        ),
        migrations.AddField(
            model_name="studentcase",
            name="schedule_event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="student_signalments",
                to="academics.academicscheduleevent",
            ),
        ),
        migrations.AddField(
            model_name="studentcase",
            name="occurred_on",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="teachercase",
            name="academic_class",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="teacher_signalments",
                to="academics.academicclass",
            ),
        ),
        migrations.AddField(
            model_name="teachercase",
            name="schedule_event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="teacher_signalments",
                to="academics.academicscheduleevent",
            ),
        ),
        migrations.AddField(
            model_name="teachercase",
            name="occurred_on",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="attendancerollsheet",
            constraint=models.UniqueConstraint(
                fields=("branch", "academic_class", "schedule_event"),
                name="students_unique_roll_sheet_branch_class_event",
            ),
        ),
    ]
