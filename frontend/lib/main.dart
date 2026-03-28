import 'dart:convert';
import 'dart:async' as java_timer;
import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:file_saver/file_saver.dart';
import 'package:universal_html/html.dart' as html;

void main() {
  runApp(const CareerLensApp());
}

class CareerLensApp extends StatelessWidget {
  const CareerLensApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CareerLens AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6366F1), // Modern Indigo
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'Inter',
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF818CF8),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        fontFamily: 'Inter',
      ),
      themeMode: ThemeMode.system,
      home: const CareerLensHome(),
    );
  }
}

class CareerLensHome extends StatefulWidget {
  const CareerLensHome({super.key});

  @override
  State<CareerLensHome> createState() => _CareerLensHomeState();
}

class _CareerLensHomeState extends State<CareerLensHome> with SingleTickerProviderStateMixin {
  final TextEditingController _resumeController = TextEditingController();
  final TextEditingController _jobDescController = TextEditingController();
  final TextEditingController _apiKeyController = TextEditingController();
  
  String _selectedSeniority = 'Mid-Level';
  final List<String> _seniorityOptions = ['Executive', 'Senior', 'Mid-Level', 'Junior', 'Entry'];
  
  bool _isLoading = false;
  int _elapsedSeconds = 0;
  java_timer.Timer? _generationTimer;
  http.Client? _activeClient;
  
  String? _generatedHtml;
  String _apiStatus = "Checking API...";

  static const String _resumePrefKey = "saved_master_resume";
  static const String _apiPrefKey = "saved_api_key";
  
  String get _backendUrl {
    if (kIsWeb) return "${Uri.base.origin}/api/v1";
    if (defaultTargetPlatform == TargetPlatform.android) return "http://10.0.2.2:8000/api/v1";
    return "http://127.0.0.1:8000/api/v1";
  }

  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000));
    _fadeAnimation = CurvedAnimation(parent: _animationController, curve: Curves.easeInOut);
    _animationController.forward();
    _loadSavedData();
    _checkApiHealth();
  }

  @override
  void dispose() {
    _animationController.dispose();
    _resumeController.dispose();
    _jobDescController.dispose();
    _apiKeyController.dispose();
    _generationTimer?.cancel();
    _activeClient?.close();
    super.dispose();
  }

  Future<void> _loadSavedData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _resumeController.text = prefs.getString(_resumePrefKey) ?? "";
      _apiKeyController.text = prefs.getString(_apiPrefKey) ?? "";
    });
  }

  Future<void> _saveData() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_resumePrefKey, _resumeController.text);
    await prefs.setString(_apiPrefKey, _apiKeyController.text);
  }

  Future<void> _checkApiHealth() async {
    try {
      final response = await http.get(Uri.parse("$_backendUrl/health")).timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() => _apiStatus = data['api_status'] ?? "Checking API...");
      }
    } catch (_) {
      setState(() => _apiStatus = "API Offline");
    }
  }

  Future<void> _generateCareerData() async {
    if (_jobDescController.text.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
      _generatedHtml = null;
      _elapsedSeconds = 0;
    });

    _generationTimer = java_timer.Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) setState(() => _elapsedSeconds++);
    });

    await _saveData();
    _activeClient = http.Client();

    try {
      final response = await _activeClient!.post(
        Uri.parse("$_backendUrl/generate"),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'job_description': _jobDescController.text.trim(),
          'master_resume': _resumeController.text.trim(),
          'target_seniority': _selectedSeniority,
          if (_apiKeyController.text.trim().isNotEmpty) 'user_api_key': _apiKeyController.text.trim(),
        }),
      );

      if (response.statusCode == 200) {
        setState(() => _generatedHtml = response.body);
      } else {
        _showError("Server Error: ${response.statusCode}\n${response.body}");
      }
    } catch (e) {
      if (e.toString().contains("cancelled")) return;
      _showError(e.toString());
    } finally {
      _generationTimer?.cancel();
      _activeClient?.close();
      setState(() => _isLoading = false);
    }
  }

  void _showError(String msg) {
    bool isModelMissing = msg.contains("No models loaded");
    
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            Icon(isModelMissing ? Icons.tips_and_updates_rounded : Icons.warning_amber_rounded, 
                 color: isModelMissing ? Colors.orangeAccent : Colors.redAccent),
            const SizedBox(width: 12),
            Text(isModelMissing ? "Action Required" : "Generation Failed"),
          ],
        ),
        content: SingleChildScrollView(
          child: ListBody(
            children: [
              if (isModelMissing) ...[
                const Text("LM Studio is reachable, but NO MODEL is loaded.", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                const SizedBox(height: 12),
                const Text("Please open LM Studio on your host PC and select a model to start the server."),
              ] else ...[
                const Text("The LLM was unable to complete your request.", style: TextStyle(fontWeight: FontWeight.bold)),
              ],
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.black12,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(msg, style: const TextStyle(fontFamily: "monospace", fontSize: 12)),
              ),
              const SizedBox(height: 16),
              if (!isModelMissing) const Text("Tip: If using Local LLM, check if LM Studio is running and 'CORS' is enabled in Server settings."),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text("CLOSE"),
          ),
        ],
      ),
    );
  }

  Future<void> _downloadHtml() async {
    if (_generatedHtml == null) return;
    try {
      final bytes = Uint8List.fromList(utf8.encode(_generatedHtml!));
      final filename = 'CareerLens_${DateTime.now().millisecondsSinceEpoch}.html';

      if (kIsWeb) {
        final blob = html.Blob([bytes], 'text/html');
        final url = html.Url.createObjectUrlFromBlob(blob);
        html.AnchorElement(href: url)..setAttribute("download", filename)..click();
        html.Url.revokeObjectUrl(url);
      } else {
        await FileSaver.instance.saveFile(name: filename, bytes: bytes, fileExtension: 'html');
      }
    } catch (e) {
      _showError(e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isWide = MediaQuery.of(context).size.width > 900;

    return Scaffold(
      body: Stack(
        children: [
          // Premium Gradient Background
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    theme.colorScheme.primary.withAlpha(50),
                    theme.colorScheme.surface,
                    theme.colorScheme.tertiary.withAlpha(30),
                  ],
                ),
              ),
            ),
          ),
          
          SafeArea(
            child: Column(
              children: [
                _buildAppBar(theme),
                Expanded(
                  child: FadeTransition(
                    opacity: _fadeAnimation,
                    child: Padding(
                      padding: const EdgeInsets.all(24.0),
                      child: isWide ? _buildWideLayout(theme) : _buildNarrowLayout(theme),
                    ),
                  ),
                ),
              ],
            ),
          ),
          
          if (_isLoading) _buildLoadingOverlay(theme),
        ],
      ),
    );
  }

  Widget _buildAppBar(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 24),
          ),
          const SizedBox(width: 16),
          Text(
            'CareerLens AI',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: theme.colorScheme.onSurface, letterSpacing: -0.5),
          ),
          _buildApiBadge(theme),
        ],
      ),
    );
  }

  Widget _buildApiBadge(ThemeData theme) {
    Color badgeColor = theme.colorScheme.outline;
    IconData badgeIcon = Icons.sensors_off_rounded;
    
    if (_apiStatus.contains("Connected")) {
      badgeColor = Colors.greenAccent.shade700;
      badgeIcon = Icons.sensors_rounded;
    } else if (_apiStatus.contains("Credits") || _apiStatus.contains("Model")) {
      badgeColor = Colors.orangeAccent.shade700;
      badgeIcon = Icons.tips_and_updates_rounded;
    } else if (_apiStatus.contains("Configured") || _apiStatus.contains("Offline")) {
      badgeColor = theme.colorScheme.outline;
      badgeIcon = Icons.sensors_off_rounded;
    } else if (_apiStatus.contains("Invalid") || _apiStatus.contains("Error")) {
      badgeColor = Colors.redAccent;
      badgeIcon = Icons.error_outline_rounded;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: badgeColor.withAlpha(40),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: badgeColor.withAlpha(100)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(badgeIcon, size: 14, color: badgeColor),
          const SizedBox(width: 8),
          Text(
            _apiStatus.toUpperCase(), 
            style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: badgeColor, letterSpacing: 0.5)
          ),
        ],
      ),
    );
  }

  Widget _buildWideLayout(ThemeData theme) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(flex: 1, child: _buildGlassCard(child: _buildInputSection(theme), theme: theme)),
        const SizedBox(width: 24),
        Expanded(flex: 1, child: _buildGlassCard(child: _buildOutputSection(theme), theme: theme)),
      ],
    );
  }

  Widget _buildNarrowLayout(ThemeData theme) {
    return SingleChildScrollView(
      child: Column(
        children: [
          _buildGlassCard(child: _buildInputSection(theme), theme: theme),
          const SizedBox(height: 24),
          _buildGlassCard(child: _buildOutputSection(theme), theme: theme),
        ],
      ),
    );
  }

  Widget _buildGlassCard({required Widget child, required ThemeData theme}) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          decoration: BoxDecoration(
            color: theme.colorScheme.surface.withAlpha(160),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: theme.colorScheme.outlineVariant.withAlpha(100)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withAlpha(10),
                blurRadius: 20,
                offset: const Offset(0, 10),
              )
            ],
          ),
          child: child,
        ),
      ),
    );
  }

  Widget _buildInputSection(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 32, 32, 0),
          child: _buildSectionHeader(theme, "INPUT DETAILS", Icons.edit_note),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildFieldLabel(theme, "Master Resume / Facts"),
                _buildModernField(_resumeController, "Paste your experience here...", 6, theme),
                const SizedBox(height: 24),
                _buildFieldLabel(theme, "Target Job Description"),
                _buildModernField(_jobDescController, "Paste the JD here...", 5, theme),
                const SizedBox(height: 24),
                _buildFieldLabel(theme, "API Configuration"),
                _buildModernField(_apiKeyController, "Optional: Gemini API Key (Blank = Local RTX)", 1, theme, isObscure: true),
                const SizedBox(height: 24),
                _buildSeniorityPicker(theme),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(32.0),
          child: SizedBox(
            width: double.infinity,
            height: 64,
            child: ElevatedButton.icon(
              onPressed: _isLoading ? null : _generateCareerData,
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                elevation: 4,
                shadowColor: theme.colorScheme.primary.withAlpha(100),
              ),
              icon: const Icon(Icons.bolt_rounded),
              label: const Text('GENERATE PROFILE', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, letterSpacing: 1.2)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildOutputSection(ThemeData theme) {
    if (_generatedHtml == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.auto_awesome_motion_outlined, size: 64, color: theme.colorScheme.outlineVariant),
            const SizedBox(height: 16),
            Text('Ready for Generation', style: TextStyle(color: theme.colorScheme.outline, fontWeight: FontWeight.bold)),
          ],
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 32, 32, 0),
          child: _buildSectionHeader(theme, "GENERATION COMPLETE", Icons.verified),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32.0),
            child: Column(
              children: [
                const SizedBox(height: 40),
                const Icon(Icons.task_alt_rounded, size: 100, color: Colors.greenAccent),
                const SizedBox(height: 32),
                Text('Your ATS Profile has been architected.', textAlign: TextAlign.center, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 16),
                Text('Processed with seniority directives for $_selectedSeniority.', textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(32.0),
          child: SizedBox(
            width: double.infinity,
            height: 64,
            child: OutlinedButton.icon(
              onPressed: _downloadHtml,
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: theme.colorScheme.primary, width: 2),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              icon: const Icon(Icons.download_rounded),
              label: const Text('DOWNLOAD HTML REPORT', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader(ThemeData theme, String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 20, color: theme.colorScheme.primary),
        const SizedBox(width: 12),
        Text(title, style: TextStyle(fontWeight: FontWeight.w900, color: theme.colorScheme.primary, fontSize: 12, letterSpacing: 1.5)),
      ],
    );
  }

  Widget _buildFieldLabel(ThemeData theme, String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0, left: 4),
      child: Text(label, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: theme.colorScheme.onSurfaceVariant)),
    );
  }

  Widget _buildModernField(TextEditingController controller, String hint, int maxLines, ThemeData theme, {bool isObscure = false}) {
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceVariant.withAlpha(80),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: theme.colorScheme.outlineVariant.withAlpha(80)),
      ),
      child: TextField(
        controller: controller,
        maxLines: maxLines,
        obscureText: isObscure,
        decoration: InputDecoration(
          hintText: hint,
          border: InputBorder.none,
          contentPadding: const EdgeInsets.all(16),
          hintStyle: TextStyle(color: theme.colorScheme.outline),
        ),
      ),
    );
  }

  Widget _buildSeniorityPicker(ThemeData theme) {
    return Row(
      children: [
        const Text("Target Level: ", style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(width: 16),
        Expanded(
          child: DropdownButton<String>(
            value: _selectedSeniority,
            underline: const SizedBox(),
            isExpanded: true,
            items: _seniorityOptions.map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
            onChanged: (v) => setState(() => _selectedSeniority = v!),
          ),
        ),
      ],
    );
  }

  Widget _buildLoadingOverlay(ThemeData theme) {
    final timeStr = "${(_elapsedSeconds / 60).floor().toString().padLeft(2, '0')}:${(_elapsedSeconds % 60).toString().padLeft(2, '0')}";
    
    return Container(
      color: Colors.black.withAlpha(180),
      child: Center(
        child: _buildGlassCard(
          theme: theme,
          child: Padding(
            padding: const EdgeInsets.all(40.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(width: 60, height: 60, child: CircularProgressIndicator(strokeWidth: 6)),
                const SizedBox(height: 32),
                Text("ARCHITECTING PROFILE", style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w900, letterSpacing: 2)),
                const SizedBox(height: 16),
                Text("Elapsed Time: $timeStr", style: const TextStyle(fontFamily: "monospace", fontSize: 18, fontWeight: FontWeight.bold)),
                if (_elapsedSeconds >= 5) ...[
                  const SizedBox(height: 32),
                  ElevatedButton.icon(
                    onPressed: () {
                      _activeClient?.close();
                      _generationTimer?.cancel();
                      setState(() => _isLoading = false);
                    },
                    icon: const Icon(Icons.cancel),
                    label: const Text("INTERRUPT GENERATION"),
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent, foregroundColor: Colors.white),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
