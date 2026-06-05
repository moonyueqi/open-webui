<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { skills } from '$lib/stores';
	import { onMount, getContext } from 'svelte';

	const i18n = getContext('i18n');

	import { createNewSkill, getSkills } from '$lib/apis/skills';
	import SkillEditor from '$lib/components/workspace/Skills/SkillEditor.svelte';

	let skill: {
		name: string;
		id: string;
		description: string;
		content: string;
		is_active: boolean;
		category_id?: string | null;
	} | null = null;

	let clone = false;
	let categoryId: string | null = null;
	let backHref = '/workspace/skills';

	const onSubmit = async (_skill) => {
		if (!_skill.category_id) {
			toast.error($i18n.t('Please select a category first.'));
			return;
		}

		const res = await createNewSkill(localStorage.token, _skill).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Skill created successfully'));
			await skills.set(await getSkills(localStorage.token));
			await goto(backHref);
		}
	};

	onMount(async () => {
		categoryId = $page.url.searchParams.get('category_id');

		if (!categoryId) {
			toast.error($i18n.t('Please select a category first.'));
			goto('/workspace/skills');
			return;
		}

		backHref = `/workspace/skills/categories/${categoryId}`;

		if (sessionStorage.skill) {
			const _skill = JSON.parse(sessionStorage.skill);
			sessionStorage.removeItem('skill');

			clone = true;
			skill = {
				name: _skill.name || 'Skill',
				id: _skill.id || '',
				description: _skill.description || '',
				content: _skill.content || '',
				is_active: _skill.is_active ?? true,
				category_id: categoryId
			};
		}
	});
</script>

{#key skill}
	<SkillEditor {skill} {onSubmit} {clone} {categoryId} {backHref} />
{/key}
