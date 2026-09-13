import re

fpath = '/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/kernel_t527_v1.13/linux/allwinner/gc_vip_kernel_drv_platform.c'
with open(fpath + '.bak_clk', 'r') as f:
    content = f.read()

# Replace lines 114 to 223
old_part_pattern = re.compile(r'#if IS_ENABLED\(CONFIG_AW_PM_DOMAINS\)\s+/\*\s+\* @brief turn on the VIP clock\..*?static vip_status_e set_vip_power_clk\(gckvip_driver_t \*kdriver, uint32_t status\)\s*\{.*?return VIP_SUCCESS;\s*\}', re.DOTALL)

new_part = r'''/*
* @brief turn on the VIP clock.
* */
static vip_status_e npu_clk_init(void)
{
	int ret;
	printk(KERN_INFO "vipcore: npu_clk_init enabling clocks and deasserting resets...\n");
	if (!IS_ERR_OR_NULL(aw_driver.bus)) {
		ret = clk_prepare_enable(aw_driver.bus);
		if (ret) {
			pr_err("vipcore: Couldn't enable bus clock: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.ahb_gate)) {
		ret = clk_prepare_enable(aw_driver.ahb_gate);
		if (ret) {
			pr_err("vipcore: Couldn't enable ahb_gate clock: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.hclk)) {
		ret = clk_prepare_enable(aw_driver.hclk);
		if (ret) {
			pr_err("vipcore: Couldn't enable AHB clock: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.aclk)) {
		ret = clk_prepare_enable(aw_driver.aclk);
		if (ret) {
			pr_err("vipcore: Couldn't enable AXI clock: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.mclk)) {
		ret = clk_prepare_enable(aw_driver.mclk);
		if (ret) {
			pr_err("vipcore: Couldn't enable module clock: %d\n", ret);
			return -EBUSY;
		}
	}

	if (!IS_ERR_OR_NULL(aw_driver.hrst)) {
		ret = reset_control_deassert(aw_driver.hrst);
		if (ret) {
			pr_err("vipcore: Couldn't deassert AHB RST: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.arst)) {
		ret = reset_control_deassert(aw_driver.arst);
		if (ret) {
			pr_err("vipcore: Couldn't deassert AXI RST: %d\n", ret);
			return -EBUSY;
		}
	}
	if (!IS_ERR_OR_NULL(aw_driver.rst)) {
		ret = reset_control_deassert(aw_driver.rst);
		if (ret) {
			pr_err("vipcore: Couldn't deassert NPU RST: %d\n", ret);
			return -EBUSY;
		}
	}
	printk(KERN_INFO "vipcore: npu_clk_init all clocks enabled and resets deasserted\n");
	return VIP_SUCCESS;
}

/*
* @brief turn off the VIP clock.
* */
static vip_status_e npu_clk_uninit(void)
{
	printk(KERN_INFO "vipcore: npu_clk_uninit asserting resets and disabling clocks...\n");
	if (!IS_ERR_OR_NULL(aw_driver.rst))
		reset_control_assert(aw_driver.rst);
	if (!IS_ERR_OR_NULL(aw_driver.arst))
		reset_control_assert(aw_driver.arst);
	if (!IS_ERR_OR_NULL(aw_driver.hrst))
		reset_control_assert(aw_driver.hrst);

	if (!IS_ERR_OR_NULL(aw_driver.mclk))
		clk_disable_unprepare(aw_driver.mclk);
	if (!IS_ERR_OR_NULL(aw_driver.aclk))
		clk_disable_unprepare(aw_driver.aclk);
	if (!IS_ERR_OR_NULL(aw_driver.hclk))
		clk_disable_unprepare(aw_driver.hclk);
	if (!IS_ERR_OR_NULL(aw_driver.ahb_gate))
		clk_disable_unprepare(aw_driver.ahb_gate);
	if (!IS_ERR_OR_NULL(aw_driver.bus))
		clk_disable_unprepare(aw_driver.bus);

	return VIP_SUCCESS;
}

/*
* @brief configure the power supply and clock of the VIP.
* @param kdriver, vip device object.
* */
static vip_status_e set_vip_power_clk(gckvip_driver_t *kdriver, uint32_t status)
{
	struct device *dev = &(kdriver->pdev->dev);
	int ret = 0;
	switch (status) {
	case CLK_ON:
		ret = pm_runtime_resume_and_get(dev);
		if (ret < 0) {
			pr_err("vipcore: pm_runtime_resume_and_get failed: %d\n", ret);
			return -EBUSY;
		}
		printk(KERN_INFO "vipcore: pm_runtime_resume_and_get SUCCESS\n");
		ret = npu_clk_init();
		if (ret != VIP_SUCCESS) {
			pm_runtime_put_sync(dev);
			return ret;
		}
		break;
	case CLK_OFF:
		npu_clk_uninit();
		pm_runtime_put_sync(dev);
		printk(KERN_INFO "vipcore: pm_runtime_put_sync SUCCESS\n");
		break;
	default:
		printk("Unsupported clk status: %u\n", status);
		break;
	}
	return VIP_SUCCESS;
}'''

content, count = old_part_pattern.subn(lambda m: new_part, content)
assert count == 1, 'Failed to replace clk part'

# Replace uninit pm_runtime_disable guard
uninit_pattern = re.compile(r'#if IS_ENABLED\(CONFIG_AW_PM_DOMAINS\)\s+pm_runtime_disable\(dev\);\s*#endif', re.DOTALL)
content, count = uninit_pattern.subn(lambda m: '\t\tpm_runtime_disable(dev);', content)
assert count == 1, 'Failed to replace uninit part'

# Replace adjust_param clk enable block
adjust_pm_pattern = re.compile(r'#if IS_ENABLED\(CONFIG_AW_PM_DOMAINS\)\s+pm_runtime_enable\(dev\);\s*#else.*?#endif', re.DOTALL)
content, count = adjust_pm_pattern.subn(lambda m: '\t\tpm_runtime_enable(dev);', content)
assert count == 1, 'Failed to replace adjust pm part'

with open(fpath, 'w') as f:
    f.write(content)

print("Patch applied cleanly!")
