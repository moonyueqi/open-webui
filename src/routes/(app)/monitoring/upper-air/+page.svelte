<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/monitoring/upper-air/lightning-jump');
	});
</script>
